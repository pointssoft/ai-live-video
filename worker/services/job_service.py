from time import perf_counter_ns

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

    @staticmethod
    def _elapsed_ms(start_ns: int) -> int:
        return round((perf_counter_ns() - start_ns) / 1_000_000)

    def execute(self, raw_input: dict, progress=None) -> dict:
        job_started = perf_counter_ns()
        stage_started = job_started
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
            motion_source = workspace / "motion.source"
            motion_normalized = workspace / "motion.normalized.mp4"
            output = workspace / "output.mp4"
            input_validation_ms = self._elapsed_ms(stage_started)
            report("DOWNLOADING")
            stage_started = perf_counter_ns()
            self.storage.download(
                contract.portrait.download_url,
                portrait,
                contract.portrait.size_bytes,
                contract.portrait.sha256,
            )
            self.storage.download(
                contract.motion_video.download_url,
                motion_source,
                contract.motion_video.size_bytes,
                contract.motion_video.sha256,
            )
            input_download_ms = self._elapsed_ms(stage_started)
            report("VALIDATING_MEDIA")
            stage_started = perf_counter_ns()
            self.media.probe_portrait(portrait)
            self.media.normalize_motion(motion_source, motion_normalized)
            self.media.probe_motion(
                motion_normalized,
                contract.motion_video.min_duration_ms,
                contract.motion_video.max_duration_ms,
            )
            media_processing_ms = self._elapsed_ms(stage_started)
            report("RUNNING_INFERENCE")
            model_timings = self.model.generate(
                portrait, motion_normalized, output, contract.inference
            )
            report("UPLOADING_OUTPUT")
            stage_started = perf_counter_ns()
            size, digest = self.storage.upload(
                contract.output.upload_url,
                output,
                contract.output.required_headers,
                min(contract.output.max_bytes, self.config.max_output_bytes),
            )
            output_upload_ms = self._elapsed_ms(stage_started)
            report("VERIFYING_OUTPUT")
            stage_started = perf_counter_ns()
            self.storage.verify_upload(contract.output.head_url, size)
            output_verification_ms = self._elapsed_ms(stage_started)
            report("COMPLETED")
            return {
                "schema_version": "1.0",
                "generation_id": str(contract.generation_id),
                "attempt_id": str(contract.attempt_id),
                "status": "completed",
                "timings": {
                    "total_worker_ms": self._elapsed_ms(job_started),
                    "input_validation_ms": input_validation_ms,
                    "input_download_ms": input_download_ms,
                    "media_processing_ms": media_processing_ms,
                    **(model_timings or {}),
                    "output_upload_ms": output_upload_ms,
                    "output_verification_ms": output_verification_ms,
                },
                "output": {
                    "object_key": contract.output.object_key,
                    "sha256": digest,
                    "content_type": "video/mp4",
                    "size_bytes": size,
                },
            }
