from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RgbFramePayload:
    width: int
    height: int
    data: bytes


def prepare_rgb_frame(frame: np.ndarray) -> RgbFramePayload:
    """Validate an RGB render and package its actual dimensions and bytes."""
    if not isinstance(frame, np.ndarray):
        raise TypeError("Rendered output must be a NumPy array.")
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError("Rendered output must have shape (height, width, 3).")
    if frame.dtype != np.uint8:
        raise TypeError("Rendered output must use uint8 RGB pixels.")

    height, width, _ = frame.shape
    if width <= 0 or height <= 0:
        raise ValueError("Rendered output dimensions must be positive.")

    contiguous = np.ascontiguousarray(frame)
    data = contiguous.tobytes()
    expected_size = width * height * 3
    if len(data) != expected_size:
        raise ValueError("Rendered RGB byte length does not match its dimensions.")

    return RgbFramePayload(width=width, height=height, data=data)
