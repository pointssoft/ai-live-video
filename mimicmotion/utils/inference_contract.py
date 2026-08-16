from __future__ import annotations

from typing import Any


class InferenceContractError(ValueError):
    """Raised before expensive model work when inference inputs violate the supported contract."""


def validate_pose_sequence(
    pose: Any, *, num_frames: int, height: int, width: int
) -> None:
    shape = tuple(pose.shape)
    if len(shape) != 4:
        raise InferenceContractError(
            f"image_pose must have shape [T, 3, H, W], got {shape}"
        )
    frames, channels, pose_height, pose_width = shape
    if frames < 2:
        raise InferenceContractError("image_pose must contain a reference pose and motion frames")
    if channels != 3:
        raise InferenceContractError(f"image_pose must have 3 channels, got {channels}")
    if frames != num_frames:
        raise InferenceContractError(
            f"num_frames ({num_frames}) must equal image_pose time dimension ({frames})"
        )
    if (pose_height, pose_width) != (height, width):
        raise InferenceContractError(
            f"image_pose spatial shape {(pose_height, pose_width)} does not match {(height, width)}"
        )
    if height % 8 or width % 8:
        raise InferenceContractError("height and width must be divisible by 8")
    is_floating = getattr(pose, "is_floating_point", None)
    if callable(is_floating) and not is_floating():
        raise InferenceContractError("image_pose must use a floating-point dtype")


def resolve_temporal_tiles(
    *, total_frames: int, requested_tile_size: int, tile_overlap: int
) -> tuple[int, list[list[int]]]:
    if total_frames < 2:
        raise InferenceContractError("at least two pose frames are required")
    if requested_tile_size < 2:
        raise InferenceContractError("tile size must be at least 2")
    effective_tile_size = min(requested_tile_size, total_frames)
    if tile_overlap < 0 or tile_overlap >= effective_tile_size:
        raise InferenceContractError(
            f"tile overlap must be between 0 and {effective_tile_size - 1}"
        )
    step = effective_tile_size - tile_overlap
    indices = [
        [0, *range(start + 1, min(start + effective_tile_size, total_frames))]
        for start in range(0, total_frames - effective_tile_size + 1, step)
    ]
    if indices[-1][-1] < total_frames - 1:
        indices.append(
            [0, *range(total_frames - effective_tile_size + 1, total_frames)]
        )
    return effective_tile_size, indices


def pipeline_pose_kwargs(
    pose: Any, *, requested_tile_size: int, tile_overlap: int
) -> dict[str, Any]:
    total_frames = int(pose.shape[0])
    height, width = int(pose.shape[-2]), int(pose.shape[-1])
    validate_pose_sequence(
        pose, num_frames=total_frames, height=height, width=width
    )
    effective_tile_size, _ = resolve_temporal_tiles(
        total_frames=total_frames,
        requested_tile_size=requested_tile_size,
        tile_overlap=tile_overlap,
    )
    return {
        "image_pose": pose,
        "num_frames": total_frames,
        "tile_size": effective_tile_size,
        "tile_overlap": tile_overlap,
        "height": height,
        "width": width,
    }
