import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from worker.config import WorkerConfig
from worker.contracts import WorkerInputV1
from worker.errors import WorkerError
from worker.services.job_service import JobService
from worker.url_security import validate_storage_url
from worker.workspace import job_workspace


def payload():
    expires = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    base = "http://storage.local/users/u/uploads/a/"
    return {
        "schema_version": "1.0",
        "generation_id": str(uuid4()),
        "attempt_id": str(uuid4()),
        "portrait": {
            "object_key": "users/u/uploads/a/source.jpg",
            "download_url": base + "source.jpg",
            "expires_at": expires,
            "content_type": "image/jpeg",
            "size_bytes": 3,
            "sha256": "a" * 64,
        },
        "motion_video": {
            "object_key": "users/u/uploads/b/source.mp4",
            "download_url": "http://storage.local/users/u/uploads/b/source.mp4",
            "expires_at": expires,
            "content_type": "video/mp4",
            "size_bytes": 3,
            "sha256": "b" * 64,
            "min_duration_ms": 5000,
            "max_duration_ms": 15000,
        },
        "output": {
            "object_key": "users/u/generations/g/attempts/1/output.mp4",
            "upload_url": "http://storage.local/users/u/generations/g/attempts/1/output.mp4",
            "head_url": "http://storage.local/users/u/generations/g/attempts/1/output.mp4",
            "expires_at": expires,
            "content_type": "video/mp4",
            "max_bytes": 1000,
            "required_headers": {"content-type": "video/mp4"},
        },
        "inference": {
            "profile": "mimicmotion-v1.1-balanced-v1",
            "profile_revision": 1,
            "model_version": "v1.1",
            "resolution": 576,
            "tile_size": 72,
            "tile_overlap": 6,
            "num_inference_steps": 25,
            "noise_aug_strength": 0.0,
            "guidance_scale": 2.0,
            "sample_stride": 2,
            "output_fps": 15,
            "seed": 42,
        },
    }


class FakeStorage:
    def download(self, url, destination, expected_size, expected_sha256):
        destination.write_bytes(b"abc")

    def upload(self, url, source, headers, max_bytes):
        return source.stat().st_size, "c" * 64

    def verify_upload(self, url, expected_size):
        self.verified_size = expected_size


class FakeModel:
    def generate(self, portrait, motion, output, profile):
        output.write_bytes(b"video")


class WorkerContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = WorkerConfig(
            "test", frozenset({"storage.local"}), Path(self.temp.name), True
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_contract_and_url(self):
        contract = WorkerInputV1.model_validate(payload())
        validate_storage_url(
            contract.portrait.download_url, contract.portrait.object_key, self.config
        )

    def test_workspace_cleanup(self):
        attempt = uuid4()
        with job_workspace(Path(self.temp.name), attempt) as path:
            self.assertTrue(path.exists())
        self.assertFalse(path.exists())

    def test_job_calls_model_once_and_returns_manifest(self):
        stages = []
        result = JobService(
            self.config, FakeStorage(), FakeModel()
        ).execute(payload(), stages.append)
        self.assertEqual(
            stages,
            [
                "VALIDATING_INPUT",
                "DOWNLOADING",
                "RUNNING_INFERENCE",
                "UPLOADING_OUTPUT",
                "VERIFYING_OUTPUT",
                "COMPLETED",
            ],
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["output"]["size_bytes"], 5)

    def test_rejects_host_suffix_attack(self):
        data = payload()
        data["portrait"]["download_url"] = (
            "http://storage.local.attacker/users/u/uploads/a/source.jpg"
        )
        contract = WorkerInputV1.model_validate(data)
        with self.assertRaises(WorkerError):
            validate_storage_url(
                contract.portrait.download_url,
                contract.portrait.object_key,
                self.config,
            )


if __name__ == "__main__":
    unittest.main()
