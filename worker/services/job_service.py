from worker.config import WorkerConfig
from worker.contracts import WorkerInputV1
from worker.errors import WorkerError
from worker.services.media_service import MediaService
from worker.services.model_service import ModelService
from worker.services.storage_service import StorageService
from worker.url_security import validate_storage_url
from worker.workspace import job_workspace


class JobService:
    def __init__(
        self, config: WorkerConfig, storage=None, model=None, media=None
    ) -> None:
        self.config = config
        self.storage = storage or StorageService()
        self.model = model or ModelService(
            config.model_root, config.artifacts_ready_path
        )
        self.media = media or MediaService()

    def execute(self, raw_input: dict, progress=None) -> dict:
        report = progress or (lambda stage: None)
        report("VALIDATING_INPUT")
        contract = WorkerInputV1.model_validate(raw_input)
        for obj in (contract.portrait, contract.motion_video):
            validate_storage_url(obj.download_url, obj.object_key, self.config)
        validate_storage_url(
            contract.output.upload_url, contract.output.object_key, self.config
        )
        validate_storage_url(
            contract.output.head_url, contract.output.object_key, self.config
        )
        if (
            contract.portrait.size_bytes > self.config.max_portrait_bytes
            or contract.motion_video.size_bytes > self.config.max_motion_bytes
        ):
            raise WorkerError(
                "INPUT_CONTRACT_INVALID",
                "VALIDATING_INPUT",
                False,
                "Input exceeds worker limits.",
            )
        with job_workspace(
            self.config.workspace_root, contract.attempt_id
        ) as workspace:
            portrait = workspace / "portrait.source"
            motion = workspace / "motion.source"
            output = workspace / "output.mp4"
            report("DOWNLOADING")
            self.storage.download(
                contract.portrait.download_url,
                portrait,
                contract.portrait.size_bytes,
                contract.portrait.sha256,
            )
            self.storage.download(
                contract.motion_video.download_url,
                motion,
                contract.motion_video.size_bytes,
                contract.motion_video.sha256,
            )
            report("VALIDATING_MEDIA")
            self.media.probe_portrait(portrait)
            self.media.probe_motion(
                motion,
                contract.motion_video.min_duration_ms,
                contract.motion_video.max_duration_ms,
            )
            report("RUNNING_INFERENCE")
            self.model.generate(portrait, motion, output, contract.inference)
            report("UPLOADING_OUTPUT")
            size, digest = self.storage.upload(
                contract.output.upload_url,
                output,
                contract.output.required_headers,
                min(contract.output.max_bytes, self.config.max_output_bytes),
            )
            report("VERIFYING_OUTPUT")
            self.storage.verify_upload(contract.output.head_url, size)
            report("COMPLETED")
            return {
                "schema_version": "1.0",
                "generation_id": str(contract.generation_id),
                "attempt_id": str(contract.attempt_id),
                "status": "completed",
                "output": {
                    "object_key": contract.output.object_key,
                    "sha256": digest,
                    "content_type": "video/mp4",
                    "size_bytes": size,
                },
            }
