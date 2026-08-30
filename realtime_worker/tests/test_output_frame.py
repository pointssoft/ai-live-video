import numpy as np
import pytest

from realtime_worker.output_frame import prepare_rgb_frame


@pytest.mark.parametrize(
    ("height", "width"),
    [
        (1024, 1024),
        (1024, 768),
        (768, 1024),
    ],
)
def test_prepare_rgb_frame_uses_rendered_dimensions(
    height: int, width: int
) -> None:
    rendered = np.zeros((height, width, 3), dtype=np.uint8)

    frame = prepare_rgb_frame(rendered)

    assert frame.width == width
    assert frame.height == height
    assert len(frame.data) == width * height * 3


def test_prepare_rgb_frame_makes_noncontiguous_render_contiguous() -> None:
    rendered = np.arange(4 * 6 * 3, dtype=np.uint8).reshape(4, 6, 3)[:, ::2, :]
    assert not rendered.flags.c_contiguous

    frame = prepare_rgb_frame(rendered)

    assert (frame.width, frame.height) == (3, 4)
    assert frame.data == np.ascontiguousarray(rendered).tobytes()


@pytest.mark.parametrize(
    "rendered",
    [
        np.zeros((4, 4), dtype=np.uint8),
        np.zeros((4, 4, 4), dtype=np.uint8),
        np.zeros((4, 4, 3), dtype=np.float32),
        np.zeros((0, 4, 3), dtype=np.uint8),
    ],
)
def test_prepare_rgb_frame_rejects_invalid_render(rendered: np.ndarray) -> None:
    with pytest.raises((TypeError, ValueError)):
        prepare_rgb_frame(rendered)
