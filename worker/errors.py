import json
import secrets
from dataclasses import dataclass


@dataclass
class WorkerError(Exception):
    code: str
    stage: str
    retryable: bool
    public_message: str

    def __str__(self) -> str:
        return json.dumps({"status": "failed", "error": {"code": self.code, "stage": self.stage, "retryable": self.retryable, "message": self.public_message, "reference_id": secrets.token_hex(8)}})
