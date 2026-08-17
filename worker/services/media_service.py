import json
import subprocess
from pathlib import Path

from worker.errors import WorkerError


class MediaService:
    def probe_portrait(self, path: Path) -> None:
        payload = self._probe(path, "PORTRAIT_INVALID")
        streams = payload.get("streams", [])
        video = next(
            (stream for stream in streams if stream.get("codec_type") == "video"), None
        )
        if (
            video is None
            or int(video.get("width", 0)) <= 0
            or int(video.get("height", 0)) <= 0
        ):
            raise WorkerError(
                "PORTRAIT_INVALID",
                "VALIDATING_MEDIA",
                False,
                "The portrait could not be decoded.",
            )

    def probe_motion(
        self, path: Path, min_duration_ms: int, max_duration_ms: int
    ) -> None:
        payload = self._probe(path, "MOTION_INVALID")
        streams = payload.get("streams", [])
        video = next(
            (stream for stream in streams if stream.get("codec_type") == "video"), None
        )
        try:
            duration_ms = round(float(payload["format"]["duration"]) * 1000)
        except (KeyError, TypeError, ValueError) as exc:
            raise WorkerError(
                "MOTION_INVALID",
                "VALIDATING_MEDIA",
                False,
                "The motion video duration could not be determined.",
            ) from exc
        if (
            video is None
            or int(video.get("width", 0)) <= 0
            or int(video.get("height", 0)) <= 0
        ):
            raise WorkerError(
                "MOTION_INVALID",
                "VALIDATING_MEDIA",
                False,
                "The motion video could not be decoded.",
            )
        if not min_duration_ms <= duration_ms <= max_duration_ms:
            raise WorkerError(
                "MOTION_DURATION_INVALID",
                "VALIDATING_MEDIA",
                False,
                "The motion video duration is outside the supported range.",
            )

    @staticmethod
    def _probe(path: Path, error_code: str) -> dict:
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration:stream=codec_type,width,height",
                    "-of",
                    "json",
                    str(path),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return json.loads(result.stdout)
        except (subprocess.SubprocessError, json.JSONDecodeError) as exc:
            raise WorkerError(
                error_code,
                "VALIDATING_MEDIA",
                False,
                "The input media could not be inspected.",
            ) from exc
