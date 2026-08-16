import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkerConfig:
    app_env: str
    allowed_storage_hosts: frozenset[str]
    workspace_root: Path
    allow_insecure_urls: bool
    model_root: Path = Path("/runpod-volume/models")
    artifacts_ready_path: Path = Path("/runpod-volume/ARTIFACTS_READY")
    max_portrait_bytes: int = 15 * 1024 * 1024
    max_motion_bytes: int = 100 * 1024 * 1024
    max_output_bytes: int = 200 * 1024 * 1024

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        hosts = frozenset(h.strip().lower() for h in os.environ["ALLOWED_STORAGE_HOSTS"].split(",") if h.strip())
        if not hosts:
            raise ValueError("ALLOWED_STORAGE_HOSTS is required")
        return cls(
            app_env=os.getenv("APP_ENV", "production"),
            allowed_storage_hosts=hosts,
            workspace_root=Path(os.getenv("WORKSPACE_ROOT", "/tmp/mimicmotion")).resolve(),
            allow_insecure_urls=os.getenv("ALLOW_INSECURE_STORAGE_URLS", "false").lower() == "true",
            model_root=Path(os.getenv("MODEL_ROOT", "/runpod-volume/models")).resolve(),
            artifacts_ready_path=Path(
                os.getenv("ARTIFACTS_READY_PATH", "/runpod-volume/ARTIFACTS_READY")
            ).resolve(),
        )
