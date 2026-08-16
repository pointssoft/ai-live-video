from pathlib import Path
from threading import Lock
from typing import ClassVar


class ModelService:
    _EXPECTED_ARTIFACTS: ClassVar[dict[str, int]] = {
        "MimicMotion_1-1.pth": 3_049_867_447,
        "DWPose/yolox_l.onnx": 216_746_733,
        "DWPose/dw-ll_ucoco_384.onnx": 134_399_116,
        "SVD/stable-video-diffusion-img2vid-xt-1-1/model_index.json": 496,
        "SVD/stable-video-diffusion-img2vid-xt-1-1/feature_extractor/preprocessor_config.json": 518,
        "SVD/stable-video-diffusion-img2vid-xt-1-1/image_encoder/config.json": 685,
        "SVD/stable-video-diffusion-img2vid-xt-1-1/image_encoder/model.fp16.safetensors": 1_264_217_240,
        "SVD/stable-video-diffusion-img2vid-xt-1-1/scheduler/scheduler_config.json": 533,
        "SVD/stable-video-diffusion-img2vid-xt-1-1/unet/config.json": 984,
        "SVD/stable-video-diffusion-img2vid-xt-1-1/vae/config.json": 607,
        "SVD/stable-video-diffusion-img2vid-xt-1-1/vae/diffusion_pytorch_model.fp16.safetensors": 195_531_910,
    }

    def __init__(
        self,
        model_root: Path = Path("/runpod-volume/models"),
        artifacts_ready_path: Path = Path("/runpod-volume/ARTIFACTS_READY"),
    ) -> None:
        self._lock = Lock()
        self._pipeline = None
        self.model_root = model_root
        self.artifacts_ready_path = artifacts_ready_path

    def _validate_artifacts(self) -> None:
        if not self.artifacts_ready_path.is_file():
            raise RuntimeError(f"Artifact marker is missing: {self.artifacts_ready_path}")
        invalid = []
        for relative_path, expected_size in self._EXPECTED_ARTIFACTS.items():
            path = self.model_root / relative_path
            actual_size = path.stat().st_size if path.is_file() else None
            if actual_size != expected_size:
                invalid.append(
                    f"{path}: expected {expected_size} bytes, got {actual_size}"
                )
        if invalid:
            raise RuntimeError("Model artifacts are incomplete:\n" + "\n".join(invalid))

    def _load(self):
        if self._pipeline is not None:
            return
        with self._lock:
            if self._pipeline is not None:
                return
            import torch
            from omegaconf import OmegaConf

            from mimicmotion.utils.loader import create_pipeline

            if not torch.cuda.is_available():
                raise RuntimeError("CUDA is required")
            self._validate_artifacts()
            config = OmegaConf.create(
                {
                    "base_model_path": str(
                        self.model_root
                        / "SVD"
                        / "stable-video-diffusion-img2vid-xt-1-1"
                    ),
                    "ckpt_path": str(self.model_root / "MimicMotion_1-1.pth"),
                }
            )
            previous_dtype = torch.get_default_dtype()
            try:
                torch.set_default_dtype(torch.float16)
                self._pipeline = create_pipeline(config, torch.device("cuda"))
            finally:
                torch.set_default_dtype(previous_dtype)

    def generate(self, portrait: Path, motion: Path, output: Path, profile) -> None:
        import os

        import torch

        os.environ["MIMICMOTION_MODEL_ROOT"] = str(self.model_root)
        from inference import preprocess, run_pipeline
        from mimicmotion.utils.utils import save_to_mp4

        self._load()
        task = type(
            "Profile",
            (),
            {
                **profile.model_dump(),
                "num_frames": profile.tile_size,
                "frames_overlap": profile.tile_overlap,
            },
        )()
        with self._lock:
            pose, image = preprocess(
                str(motion), str(portrait), profile.resolution, profile.sample_stride
            )
            frames = run_pipeline(
                self._pipeline, image, pose, torch.device("cuda"), task
            )
            save_to_mp4(frames, str(output), fps=profile.output_fps)
