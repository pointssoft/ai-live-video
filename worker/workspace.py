import shutil
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from worker.errors import WorkerError


@contextmanager
def job_workspace(root: Path, attempt_id: UUID):
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / str(attempt_id)
    try:
        path.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise WorkerError("WORKSPACE_CONFLICT", "VALIDATING_INPUT", True, "Worker workspace is unavailable.") from exc
    (path / ".owner").write_text(str(attempt_id), encoding="utf-8")
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
