from functools import lru_cache

from pydantic import ValidationError

from worker.config import WorkerConfig
from worker.errors import WorkerError
from worker.services.job_service import JobService


@lru_cache
def application() -> JobService:
    return JobService(WorkerConfig.from_env())


def handler(job: dict) -> dict:
    try:
        job_id = job.get("id")

        def progress(stage: str) -> None:
            if job_id:
                import runpod

                runpod.serverless.progress_update(job, stage)

        return application().execute(job.get("input", {}), progress)
    except WorkerError:
        raise
    except ValidationError as exc:
        raise WorkerError(
            "INPUT_CONTRACT_INVALID",
            "VALIDATING_INPUT",
            False,
            "The worker input contract is invalid.",
        ) from exc
    except Exception as exc:
        raise WorkerError(
            "INTERNAL_WORKER_ERROR",
            "UNKNOWN",
            True,
            "The worker could not complete the job.",
        ) from exc


if __name__ == "__main__":
    import os

    mode = os.getenv("WORKER_MODE")
    if mode in {"model-smoke", "inference-smoke"}:
        from worker.smoke import run_inference_smoke, run_model_smoke

        if mode == "inference-smoke":
            run_inference_smoke()
        else:
            run_model_smoke()
    else:
        import runpod

        runpod.serverless.start({"handler": handler})
