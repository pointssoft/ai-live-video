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


@dataclass
class SourceState:
    image: np.ndarray
    crop_info: dict[str, object]
    source_info: dict[str, torch.Tensor]
    source_keypoints: torch.Tensor
    source_rotation: torch.Tensor
    source_features: torch.Tensor
    mask: np.ndarray


class RealtimeLivePortrait:
    """Thin streaming adapter around the official LivePortrait inference modules."""

    def __init__(self) -> None:
        inference = InferenceConfig(
            flag_use_half_precision=True,
            flag_do_torch_compile=True,
            flag_normalize_lip=True,
            flag_eye_retargeting=True,
            flag_lip_retargeting=True,
            flag_stitching=True,
            flag_relative_motion=True,
            flag_pasteback=True,
            flag_do_crop=True,
        )
        self.pipeline = LivePortraitPipeline(inference, CropConfig())
        self.wrapper = self.pipeline.live_portrait_wrapper
        self.cropper = self.pipeline.cropper
        self.source: SourceState | None = None
        self.initial_driving: dict[str, torch.Tensor] | None = None
        self.initial_driving_rotation: torch.Tensor | None = None

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
        self.source = SourceState(
            image=image,
            crop_info=crop_info,
            source_info=source_info,
            source_keypoints=source_keypoints,
            source_rotation=source_rotation,
            source_features=source_features,
            mask=mask,
        )
        self.initial_driving = None
        self.initial_driving_rotation = None
        return image.shape[1], image.shape[0]

    @torch.inference_mode()
    def render(self, driving_rgb: np.ndarray) -> np.ndarray | None:
        source = self.source
        if source is None:
            raise RuntimeError("A source portrait must be loaded first.")

        driving_crop = self.cropper.crop_source_image(driving_rgb, self.cropper.crop_cfg)
        if driving_crop is None:
            return source.image
        driving_input = self.wrapper.prepare_source(driving_crop["img_crop_256x256"])
        driving_info = self.wrapper.get_kp_info(driving_input)
        driving_rotation = get_rotation_matrix(
            driving_info["pitch"], driving_info["yaw"], driving_info["roll"]
        )
        if self.initial_driving is None:
            self.initial_driving = {key: value.clone() for key, value in driving_info.items()}
            self.initial_driving_rotation = driving_rotation.clone()

        initial = self.initial_driving
        initial_rotation = self.initial_driving_rotation
        if initial_rotation is None:
            return None

        rotation = (driving_rotation @ initial_rotation.permute(0, 2, 1)) @ source.source_rotation
        expression = source.source_info["exp"] + (driving_info["exp"] - initial["exp"])
        scale = source.source_info["scale"] * (driving_info["scale"] / initial["scale"])
        translation = source.source_info["t"] + (driving_info["t"] - initial["t"])
        translation[..., 2].fill_(0)
        keypoints = scale * (source.source_info["kp"] @ rotation + expression) + translation
        keypoints = self.wrapper.stitching(source.source_keypoints, keypoints)

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
        return np.ascontiguousarray(frame, dtype=np.uint8)


def decode_image(content: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("The portrait response was not a supported image.")
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
