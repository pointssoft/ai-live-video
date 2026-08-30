from dataclasses import dataclass

import cv2
import numpy as np
import torch
from src.config.crop_config import CropConfig
from src.config.inference_config import InferenceConfig
from src.live_portrait_pipeline import LivePortraitPipeline
from src.utils.camera import get_rotation_matrix
from src.utils.crop import paste_back, prepare_paste_back
from src.utils.io import resize_to_limit

from realtime_worker.motion import (
    FacialControls,
    MotionConfig,
    MotionState,
    apply_facial_controls,
    limit_stitching_delta,
)


@dataclass
class SourceState:
    image: np.ndarray
    crop_info: dict[str, object]
    source_info: dict[str, torch.Tensor]
    source_keypoints: torch.Tensor
    source_rotation: torch.Tensor
    source_features: torch.Tensor
    mask: np.ndarray
    last_rendered: np.ndarray | None = None


class RealtimeLivePortrait:
    """Thin streaming adapter around the official LivePortrait inference modules."""

    def __init__(self) -> None:
        inference = InferenceConfig(
            flag_use_half_precision=True,
            flag_do_torch_compile=False,
            flag_normalize_lip=False,
            flag_eye_retargeting=False,
            flag_lip_retargeting=False,
            flag_stitching=True,
            flag_relative_motion=True,
            flag_pasteback=True,
            flag_do_crop=True,
        )
        self.pipeline = LivePortraitPipeline(inference, CropConfig())
        self.wrapper = self.pipeline.live_portrait_wrapper
        self.cropper = self.pipeline.cropper
        self.motion = MotionState(MotionConfig())
        self.facial_controls = FacialControls()
        self.source: SourceState | None = None

    def reset_facial_controls(self) -> None:
        self.facial_controls = FacialControls()

    def set_facial_controls(
        self,
        eye_openness: object,
        mouth_openness: object,
    ) -> bool:
        controls = FacialControls.from_values(eye_openness, mouth_openness)
        if controls is None:
            return False
        self.facial_controls = controls
        return True

    def set_source(self, image_rgb: np.ndarray) -> tuple[int, int]:
        config = self.wrapper.inference_cfg
        image = resize_to_limit(image_rgb, config.source_max_dim, config.source_division)
        crop_info = self.cropper.crop_source_image(image, self.cropper.crop_cfg)
        if crop_info is None:
            raise ValueError("No face was detected in the portrait.")

        source_input = self.wrapper.prepare_source(crop_info["img_crop_256x256"])
        source_info = self.wrapper.get_kp_info(source_input)
        source_rotation = get_rotation_matrix(
            source_info["pitch"], source_info["yaw"], source_info["roll"]
        )
        source_keypoints = self.wrapper.transform_keypoint(source_info)
        source_features = self.wrapper.extract_feature_3d(source_input)
        mask = prepare_paste_back(
            config.mask_crop,
            crop_info["M_c2o"],
            dsize=(image.shape[1], image.shape[0]),
        )
        self.motion.reset()
        self.source = SourceState(
            image=image,
            crop_info=crop_info,
            source_info=source_info,
            source_keypoints=source_keypoints,
            source_rotation=source_rotation,
            source_features=source_features,
            mask=mask,
        )
        return image.shape[1], image.shape[0]

    @torch.inference_mode()
    def render(self, driving_rgb: np.ndarray) -> np.ndarray | None:
        source = self.source
        if source is None:
            raise RuntimeError("A source portrait must be loaded first.")

        driving_crop = self.cropper.crop_source_image(driving_rgb, self.cropper.crop_cfg)
        if driving_crop is None:
            if source.last_rendered is not None:
                return source.last_rendered
            return source.image

        driving_input = self.wrapper.prepare_source(driving_crop["img_crop_256x256"])
        driving_info = self.wrapper.get_kp_info(driving_input)
        driving_rotation = get_rotation_matrix(
            driving_info["pitch"], driving_info["yaw"], driving_info["roll"]
        )
        if not self.motion.update(driving_info, driving_rotation):
            if source.last_rendered is not None:
                return source.last_rendered
            return source.image
        rotation, expression, scale, translation = self.motion.target_motion(
            source.source_info,
            source.source_rotation,
            source.source_keypoints,
        )
        expression = apply_facial_controls(expression, self.facial_controls)

        # This mirrors the official wrapper.transform_keypoint operation while
        # allowing relative driving rotation to be composed with source rotation.
        keypoints = _transform_keypoints(
            source.source_info["kp"],
            rotation,
            expression,
            scale,
            translation,
        )
        stitched_keypoints = self.wrapper.stitching(
            source.source_keypoints,
            keypoints,
        )
        keypoints = limit_stitching_delta(
            source.source_keypoints,
            keypoints,
            stitched_keypoints,
            self.motion.config,
        )

        output = self.wrapper.warp_decode(
            source.source_features, source.source_keypoints, keypoints
        )
        crop = self.wrapper.parse_output(output["out"])[0]
        frame = paste_back(
            crop,
            source.crop_info["M_c2o"],
            source.image,
            source.mask,
        )
        source.last_rendered = np.ascontiguousarray(frame, dtype=np.uint8)
        return source.last_rendered


def _transform_keypoints(
    canonical_keypoints: torch.Tensor,
    rotation: torch.Tensor,
    expression: torch.Tensor,
    scale: torch.Tensor,
    translation: torch.Tensor,
) -> torch.Tensor:
    """Apply the pinned LivePortrait keypoint transform with explicit batching."""
    batch_size = canonical_keypoints.shape[0]
    canonical_keypoints = canonical_keypoints.reshape(batch_size, -1, 3)
    expression = expression.reshape(batch_size, -1, 3)
    transformed = canonical_keypoints @ rotation + expression
    transformed = transformed * scale.reshape(batch_size, 1, 1)
    transformed[..., :2] += translation.reshape(batch_size, 1, 3)[..., :2]
    return transformed


def decode_image(content: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("The portrait response was not a supported image.")
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
