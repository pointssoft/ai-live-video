import asyncio
import json
import logging

import httpx
import numpy as np
from livekit import agents, rtc

from realtime_worker.config import Settings
from realtime_worker.liveportrait import RealtimeLivePortrait, decode_image

logger = logging.getLogger("realtime-worker")


def prewarm(proc: agents.JobProcess) -> None:
    proc.userdata["renderer"] = RealtimeLivePortrait()


async def entrypoint(ctx: agents.JobContext) -> None:
    stage = "connect"
    participant_identity: str | None = None
    stream: rtc.VideoStream | None = None
    logger.info("realtime_job_started")

    try:
        await ctx.connect(auto_subscribe=agents.AutoSubscribe.VIDEO_ONLY)
        logger.info("realtime_room_connected", extra={"room_name": ctx.room.name})

        stage = "wait_for_participant"
        participant = await ctx.wait_for_participant()
        participant_identity = participant.identity
        logger.info(
            "realtime_participant_joined",
            extra={"participant_identity": participant_identity},
        )

        stage = "read_participant_metadata"
        try:
            metadata = json.loads(participant.metadata or "{}")
            portrait_url = metadata["portrait_url"]
        except (json.JSONDecodeError, KeyError) as exc:
            raise RuntimeError(
                "Browser participant metadata has no portrait URL."
            ) from exc

        stage = "download_portrait"
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.get(portrait_url)
            response.raise_for_status()
        logger.info(
            "realtime_portrait_downloaded",
            extra={"portrait_bytes": len(response.content)},
        )

        stage = "prepare_portrait"
        renderer = ctx.proc.userdata["renderer"]
        if not isinstance(renderer, RealtimeLivePortrait):
            raise TypeError("LivePortrait did not initialize correctly.")
        width, height = renderer.set_source(decode_image(response.content))
        logger.info(
            "realtime_portrait_prepared",
            extra={"frame_width": width, "frame_height": height},
        )

        stage = "publish_output_track"
        source = rtc.VideoSource(width, height)
        output_track = rtc.LocalVideoTrack.create_video_track(
            "liveportrait-output", source
        )
        options = rtc.TrackPublishOptions()
        options.source = rtc.TrackSource.SOURCE_CAMERA
        await ctx.room.local_participant.publish_track(output_track, options)
        logger.info("realtime_output_track_published")

        # Handle data messages for portrait changes
        @ctx.room.on("data_received")
        def on_data_received(data: rtc.DataPacket):
            try:
                message = json.loads(data.data.decode("utf-8"))
                if message.get("type") == "change_portrait":
                    new_portrait_url = message.get("portrait_url")
                    if new_portrait_url:
                        logger.info("Changing portrait to: %s", new_portrait_url)
                        # Schedule portrait change in background
                        asyncio.create_task(
                            _change_portrait(renderer, new_portrait_url, source)
                        )
            except Exception:
                logger.exception("Error processing data message")

        stage = "stream_camera_frames"
        stream = rtc.VideoStream.from_participant(
            participant=participant,
            track_source=rtc.TrackSource.SOURCE_CAMERA,
            format=rtc.VideoBufferType.RGB24,
            capacity=1,
        )
        frames_processed = 0
        async for event in stream:
            stage = "render_camera_frame"
            incoming = event.frame
            frame = np.frombuffer(incoming.data, dtype=np.uint8).reshape(
                incoming.height, incoming.width, 3
            )
            rendered = renderer.render(frame)
            if rendered is None:
                stage = "stream_camera_frames"
                continue

            stage = "capture_output_frame"
            source.capture_frame(
                rtc.VideoFrame(
                    width=width,
                    height=height,
                    type=rtc.VideoBufferType.RGB24,
                    data=rendered.tobytes(),
                ),
                timestamp_us=event.timestamp_us,
            )
            frames_processed += 1
            if frames_processed == 1:
                logger.info("realtime_first_output_frame_captured")
            stage = "stream_camera_frames"
    except Exception:
        logger.exception(
            "realtime_job_failed",
            extra={
                "stage": stage,
                "participant_identity": participant_identity,
            },
        )
        raise
    finally:
        if stream is not None:
            await stream.aclose()
        logger.info(
            "realtime_session_ended",
            extra={"participant_identity": participant_identity},
        )


async def _change_portrait(
    renderer: RealtimeLivePortrait,
    portrait_url: str,
    source: rtc.VideoSource,
) -> None:
    """Load a new portrait and update the video source dimensions if needed."""
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.get(portrait_url)
            response.raise_for_status()

        width, height = renderer.set_source(decode_image(response.content))
        # Note: VideoSource dimensions are set at creation and can't be changed
        # The renderer will handle different sized portraits internally
        logger.info("Portrait changed successfully to dimensions: %sx%s", width, height)
    except Exception:
        logger.exception("Failed to change portrait")


def main() -> None:
    settings = Settings.from_env()
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name=settings.agent_name,
            ws_url=settings.livekit_url,
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
            num_idle_processes=1,
            load_threshold=0.9,
            job_memory_warn_mb=4000,
        )
    )


if __name__ == "__main__":
    main()
