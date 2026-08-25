from dataclasses import dataclass, field
from typing import Mapping

import torch


@dataclass(frozen=True)
class MotionConfig:
    """Conservative defaults for responsive, source-preserving live motion."""

    expression_alpha: float = 0.45
    pose_alpha: float = 0.30
    scale_alpha: float = 0.25
    translation_alpha: float = 0.25
    expression_gain: float = 0.80
    pose_gain: float = 0.80
    scale_gain: float = 0.20
    translation_x_gain: float = 0.35
    translation_y_gain: float = 0.20
    min_scale_ratio: float = 0.85
    max_scale_ratio: float = 1.15
    max_expression_extent_ratio: float = 0.55
    max_translation_extent_ratio: float = 0.50
    max_stitch_extent_ratio: float = 0.20


@dataclass
class MotionState:
    """Neutral reference and temporally stabilized driver motion for one session."""

    config: MotionConfig = field(default_factory=MotionConfig)
    neutral_info: dict[str, torch.Tensor] | None = None
    neutral_rotation: torch.Tensor | None = None
    smoothed_expression: torch.Tensor | None = None
    smoothed_scale: torch.Tensor | None = None
    smoothed_translation: torch.Tensor | None = None
    smoothed_rotation: torch.Tensor | None = None

    def reset(self) -> None:
        self.neutral_info = None
        self.neutral_rotation = None
        self.smoothed_expression = None
        self.smoothed_scale = None
        self.smoothed_translation = None
        self.smoothed_rotation = None

    @property
    def initialized(self) -> bool:
        return self.neutral_info is not None and self.neutral_rotation is not None

    def update(
        self,
        driving_info: Mapping[str, torch.Tensor],
        driving_rotation: torch.Tensor,
    ) -> bool:
        """Record the first driver as neutral and smooth subsequent observations."""
        _require_motion_keys(driving_info)
        if not self.initialized and not all(
            _is_finite(value)
            for value in (
                driving_info["exp"],
                driving_info["scale"],
                driving_info["t"],
                driving_rotation,
            )
        ):
            return False

        current_expression = _finite_tensor(
            driving_info["exp"], self.smoothed_expression
        )
        current_scale = _finite_tensor(driving_info["scale"], self.smoothed_scale)
        current_translation = _finite_tensor(
            driving_info["t"], self.smoothed_translation
        )
        current_rotation = _project_rotation(
            _finite_tensor(driving_rotation, self.smoothed_rotation)
        )

        if not self.initialized:
            self.neutral_info = {
                key: value.detach().clone()
                for key, value in driving_info.items()
                if torch.is_tensor(value)
            }
            self.neutral_info["exp"] = current_expression.clone()
            self.neutral_info["scale"] = current_scale.clone()
            self.neutral_info["t"] = current_translation.clone()
            self.neutral_rotation = current_rotation.clone()
            self.smoothed_expression = current_expression.clone()
            self.smoothed_scale = current_scale.clone()
            self.smoothed_translation = current_translation.clone()
            self.smoothed_rotation = current_rotation.clone()
            return True

        assert self.smoothed_expression is not None
        assert self.smoothed_scale is not None
        assert self.smoothed_translation is not None
        assert self.smoothed_rotation is not None
        self.smoothed_expression = _ema(
            self.smoothed_expression, current_expression, self.config.expression_alpha
        )
        self.smoothed_scale = _ema(
            self.smoothed_scale, current_scale, self.config.scale_alpha
        )
        self.smoothed_translation = _ema(
            self.smoothed_translation,
            current_translation,
            self.config.translation_alpha,
        )
        blended_rotation = _ema(
            self.smoothed_rotation, current_rotation, self.config.pose_alpha
        )
        self.smoothed_rotation = _project_rotation(blended_rotation)
        return True

    def target_motion(
        self,
        source_info: Mapping[str, torch.Tensor],
        source_rotation: torch.Tensor,
        source_keypoints: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """Build bounded source-relative rotation, expression, scale, and translation."""
        if not self.initialized:
            raise RuntimeError("Driver motion has not been initialized.")
        _require_motion_keys(source_info)
        assert self.neutral_info is not None
        assert self.neutral_rotation is not None
        assert self.smoothed_expression is not None
        assert self.smoothed_scale is not None
        assert self.smoothed_translation is not None
        assert self.smoothed_rotation is not None

        source_extent = _face_extent(source_keypoints)
        neutral_expression = self.neutral_info["exp"]
        expression_delta = self.smoothed_expression - neutral_expression
        expression_delta = _limit_vectors(
            expression_delta,
            source_extent * self.config.max_expression_extent_ratio,
        )
        expression = source_info["exp"] + expression_delta * self.config.expression_gain

        neutral_scale = self.neutral_info["scale"].clamp_min(torch.finfo(self.neutral_info["scale"].dtype).eps)
        scale_ratio = self.smoothed_scale / neutral_scale
        scale_ratio = torch.nan_to_num(scale_ratio, nan=1.0, posinf=1.0, neginf=1.0)
        scale_ratio = scale_ratio.clamp(
            min=self.config.min_scale_ratio,
            max=self.config.max_scale_ratio,
        )
        scale_ratio = 1.0 + (scale_ratio - 1.0) * self.config.scale_gain
        scale = source_info["scale"] * scale_ratio

        translation_delta = self.smoothed_translation - self.neutral_info["t"]
        translation_delta = _limit_vectors(
            translation_delta,
            source_extent * self.config.max_translation_extent_ratio,
        )
        translation_gain = translation_delta.new_tensor(
            [
                self.config.translation_x_gain,
                self.config.translation_y_gain,
                0.0,
            ]
        )
        translation = source_info["t"] + translation_delta * translation_gain
        translation = translation.clone()
        translation[..., 2] = 0

        relative_rotation = self.smoothed_rotation @ self.neutral_rotation.transpose(-1, -2)
        relative_rotation = _blend_rotation(
            relative_rotation,
            self.config.pose_gain,
        )
        rotation = relative_rotation @ source_rotation
        return rotation, expression, scale, translation


def limit_stitching_delta(
    source_keypoints: torch.Tensor,
    target_keypoints: torch.Tensor,
    stitched_keypoints: torch.Tensor,
    config: MotionConfig = MotionConfig(),
) -> torch.Tensor:
    """Keep learned seam correction from changing the face geometry wholesale."""
    correction = torch.nan_to_num(
        stitched_keypoints - target_keypoints,
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )
    correction = _limit_vectors(
        correction,
        _face_extent(source_keypoints) * config.max_stitch_extent_ratio,
    )
    return target_keypoints + correction


def _require_motion_keys(info: Mapping[str, torch.Tensor]) -> None:
    missing = [key for key in ("exp", "scale", "t") if key not in info]
    if missing:
        raise ValueError(f"Motion information is missing: {', '.join(missing)}")


def _is_finite(value: torch.Tensor) -> bool:
    return torch.is_tensor(value) and bool(torch.isfinite(value).all())


def _finite_tensor(
    value: torch.Tensor,
    fallback: torch.Tensor | None = None,
) -> torch.Tensor:
    if not torch.is_tensor(value):
        raise TypeError("LivePortrait motion values must be torch tensors.")
    if fallback is None:
        return torch.nan_to_num(value.detach(), nan=0.0, posinf=0.0, neginf=0.0)
    finite = torch.isfinite(value)
    return torch.where(finite, value.detach(), fallback)


def _ema(previous: torch.Tensor, current: torch.Tensor, alpha: float) -> torch.Tensor:
    return previous + (current - previous) * alpha


def _face_extent(keypoints: torch.Tensor) -> torch.Tensor:
    extent = keypoints.amax(dim=-2) - keypoints.amin(dim=-2)
    return torch.linalg.vector_norm(extent, dim=-1, keepdim=True).clamp_min(1e-4)


def _limit_vectors(values: torch.Tensor, limit: torch.Tensor) -> torch.Tensor:
    magnitude = torch.linalg.vector_norm(values, dim=-1, keepdim=True)
    while limit.ndim < magnitude.ndim:
        limit = limit.unsqueeze(-1)
    factor = (limit / magnitude.clamp_min(1e-6)).clamp(max=1.0)
    return values * factor


def _project_rotation(rotation: torch.Tensor) -> torch.Tensor:
    """Project an EMA matrix back onto SO(3), including half-precision inputs."""
    original_dtype = rotation.dtype
    matrix = rotation.float()
    u, _, vh = torch.linalg.svd(matrix)
    projected = u @ vh
    determinant = torch.linalg.det(projected)
    correction = torch.ones_like(determinant)
    correction = torch.where(determinant < 0, -correction, correction)
    u = u.clone()
    u[..., :, -1] *= correction.unsqueeze(-1)
    projected = u @ vh
    return projected.to(dtype=original_dtype)


def _blend_rotation(rotation: torch.Tensor, gain: float) -> torch.Tensor:
    identity = torch.eye(
        rotation.shape[-1],
        device=rotation.device,
        dtype=rotation.dtype,
    )
    identity = identity.expand(rotation.shape[:-2] + identity.shape)
    return _project_rotation(identity + (rotation - identity) * gain)
