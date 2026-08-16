import asyncio
import json
import warnings
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from app.core.config import Settings


class MediaValidationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class ValidationResult:
    detected_content_type: str
    width: int
    height: int
    duration_ms: int | None = None
    fps: float | None = None
    frame_count: int | None = None
    video_codec: str | None = None


def detect_content_type(path: Path) -> str:
    with path.open("rb") as source:
        header = source.read(32)
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"
    if header.startswith(b"\x1aE\xdf\xa3"):
        return "video/webm"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return "video/mp4"
    raise MediaValidationError("MEDIA_INVALID", "The uploaded file format is not recognized.")


def validate_portrait(path: Path, declared_type: str, settings: Settings) -> ValidationResult:
    detected = detect_content_type(path)
    if detected != declared_type or detected not in {"image/jpeg", "image/png", "image/webp"}:
        raise MediaValidationError("MEDIA_TYPE_MISMATCH", "The portrait file type does not match.")
    Image.MAX_IMAGE_PIXELS = settings.PORTRAIT_MAX_PIXELS
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                if getattr(image, "n_frames", 1) != 1:
                    raise MediaValidationError(
                        "PORTRAIT_INVALID", "Animated portraits are not supported."
                    )
                image.load()
                if image.mode not in {"RGB", "RGBA", "L", "LA", "P"}:
                    raise MediaValidationError(
                        "PORTRAIT_INVALID", "This portrait color format is not supported."
                    )
                normalized = ImageOps.exif_transpose(image)
                width, height = normalized.size
    except MediaValidationError:
        raise
    except (
        OSError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise MediaValidationError("PORTRAIT_INVALID", "The portrait image is invalid.") from exc
    if min(width, height) < settings.PORTRAIT_MIN_DIMENSION:
        raise MediaValidationError(
            "PORTRAIT_TOO_SMALL",
            f"Portrait dimensions must be at least {settings.PORTRAIT_MIN_DIMENSION} pixels.",
        )
    if (
        max(width, height) > settings.PORTRAIT_MAX_DIMENSION
        or width * height > settings.PORTRAIT_MAX_PIXELS
    ):
        raise MediaValidationError("PORTRAIT_TOO_LARGE", "The portrait dimensions are too large.")
    return ValidationResult(detected_content_type=detected, width=width, height=height)


async def _run_process(*args: str, timeout_seconds: int) -> tuple[int, bytes, bytes]:
    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise MediaValidationError(
            "VALIDATION_TEMPORARILY_UNAVAILABLE", "The video validator is unavailable."
        ) from exc
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except TimeoutError as exc:
        process.kill()
        await process.wait()
        raise MediaValidationError("VIDEO_DECODE_FAILED", "Video validation timed out.") from exc
    return process.returncode or 0, stdout[:1_000_000], stderr[:16_384]


def _positive_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise MediaValidationError("MEDIA_INVALID", "Video metadata is invalid.") from exc
    if parsed <= 0:
        raise MediaValidationError("MEDIA_INVALID", "Video metadata is invalid.")
    return parsed


def _fps(value: Any) -> float:
    try:
        parsed = float(Fraction(str(value)))
    except (ValueError, ZeroDivisionError) as exc:
        raise MediaValidationError("MEDIA_INVALID", "Video frame rate is invalid.") from exc
    if parsed <= 0 or parsed > 240:
        raise MediaValidationError("MEDIA_INVALID", "Video frame rate is invalid.")
    return parsed


async def validate_motion(path: Path, declared_type: str, settings: Settings) -> ValidationResult:
    detected = detect_content_type(path)
    if detected != declared_type or detected not in {"video/mp4", "video/webm"}:
        raise MediaValidationError("MEDIA_TYPE_MISMATCH", "The motion file type does not match.")
    code, stdout, _ = await _run_process(
        "ffprobe",
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-count_frames",
        "-of",
        "json",
        str(path),
        timeout_seconds=settings.MEDIA_VALIDATION_TIMEOUT_SECONDS,
    )
    if code != 0:
        raise MediaValidationError("MEDIA_INVALID", "The motion video is invalid.")
    try:
        metadata = json.loads(stdout)
        streams = [
            stream
            for stream in metadata.get("streams", [])
            if stream.get("codec_type") == "video"
            and not int(stream.get("disposition", {}).get("attached_pic", 0))
        ]
        if len(streams) != 1:
            raise MediaValidationError(
                "MEDIA_INVALID", "The motion clip must contain exactly one video stream."
            )
        stream = streams[0]
        width = _positive_int(stream.get("width"))
        height = _positive_int(stream.get("height"))
        codec = str(stream.get("codec_name", ""))
        allowed_codecs = {"video/mp4": {"h264"}, "video/webm": {"vp8", "vp9"}}
        if codec not in allowed_codecs[detected]:
            raise MediaValidationError(
                "VIDEO_CODEC_UNSUPPORTED", "The video codec is not supported."
            )
        duration_value = stream.get("duration") or metadata.get("format", {}).get("duration")
        duration_ms = round(float(duration_value) * 1000)
        frame_count = _positive_int(stream.get("nb_read_frames") or stream.get("nb_frames"))
        fps = _fps(stream.get("avg_frame_rate") or stream.get("r_frame_rate"))
    except MediaValidationError:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MediaValidationError("MEDIA_INVALID", "Video metadata is invalid.") from exc
    if max(width, height) > settings.MOTION_MAX_DIMENSION:
        raise MediaValidationError(
            "VIDEO_DIMENSIONS_UNSUPPORTED", "Video dimensions are too large."
        )
    if not settings.MOTION_MIN_DURATION_MS <= duration_ms <= settings.MOTION_MAX_DURATION_MS:
        raise MediaValidationError(
            "DURATION_OUT_OF_RANGE", "The motion clip must be between 5 and 15 seconds."
        )
    decode_code, _, _ = await _run_process(
        "ffmpeg",
        "-v",
        "error",
        "-xerror",
        "-i",
        str(path),
        "-map",
        "0:v:0",
        "-an",
        "-f",
        "null",
        "-",
        timeout_seconds=settings.MEDIA_VALIDATION_TIMEOUT_SECONDS,
    )
    if decode_code != 0:
        raise MediaValidationError("VIDEO_DECODE_FAILED", "The motion video could not be decoded.")
    return ValidationResult(
        detected_content_type=detected,
        width=width,
        height=height,
        duration_ms=duration_ms,
        fps=fps,
        frame_count=frame_count,
        video_codec=codec,
    )
