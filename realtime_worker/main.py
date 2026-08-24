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
    await ctx.connect(auto_subscribe=agents.AutoSubscribe.VIDEO_ONLY)
    participant = await ctx.wait_for_participant()
    try:
        metadata = json.loads(participant.metadata or "{}")
        portrait_url = metadata["portrait_url"]
    except (json.JSONDecodeError, KeyError) as exc:
        raise RuntimeError("Browser participant metadata has no portrait URL.") from exc

    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        response = await client.get(portrait_url)
        response.raise_for_status()

    renderer = ctx.proc.userdata["renderer"]
    if not isinstance(renderer, RealtimeLivePortrait):
        raise TypeError("LivePortrait did not initialize correctly.")
    width, height = renderer.set_source(decode_image(response.content))
    source = rtc.VideoSource(width, height)
    output_track = rtc.LocalVideoTrack.create_video_track("liveportrait-output", source)
    options = rtc.TrackPublishOptions()
    options.source = rtc.TrackSource.SOURCE_CAMERA
    await ctx.room.local_participant.publish_track(output_track, options)

    # Handle data messages for portrait changes
    @ctx.room.on("data_received")
    def on_data_received(data: rtc.DataPacket):
        try:
            message = json.loads(data.data.decode('utf-8'))
            if message.get("type") == "change_portrait":
                new_portrait_url = message.get("portrait_url")
                if new_portrait_url:
                    logger.info(f"Changing portrait to: {new_portrait_url}")
                    # Schedule portrait change in background
                    ctx.create_task(_change_portrait(renderer, new_portrait_url, source))
        except Exception as e:
            logger.error(f"Error processing data message: {e}")

    stream = rtc.VideoStream.from_participant(
        participant=participant,
        track_source=rtc.TrackSource.SOURCE_CAMERA,
        format=rtc.VideoBufferType.RGB24,
        capacity=1,
    )
    try:
        async for event in stream:
            incoming = event.frame
            frame = np.frombuffer(incoming.data, dtype=np.uint8).reshape(
                incoming.height, incoming.width, 3
            )
            rendered = renderer.render(frame)
            if rendered is None:
                continue
            source.capture_frame(
                rtc.VideoFrame(
                    width=width,
                    height=height,
                    type=rtc.VideoBufferType.RGB24,
                    data=rendered.tobytes(),
                ),
                timestamp_us=event.timestamp_us,
            )
    finally:
        await stream.aclose()
        logger.info("Realtime session ended", extra={"participant": participant.identity})


async def _change_portrait(renderer: RealtimeLivePortrait, portrait_url: str, source: rtc.VideoSource) -> None:
    """Load a new portrait and update the video source dimensions if needed."""
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.get(portrait_url)
            response.raise_for_status()

        width, height = renderer.set_source(decode_image(response.content))
        # Note: VideoSource dimensions are set at creation and can't be changed
        # The renderer will handle different sized portraits internally
        logger.info(f"Portrait changed successfully to dimensions: {width}x{height}")
    except Exception as e:
        logger.error(f"Failed to change portrait: {e}")


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
