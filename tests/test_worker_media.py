import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from worker.errors import WorkerError
from worker.services.media_service import MediaService


class MediaServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = MediaService()
        self.path = Path("input.media")

    @staticmethod
    def completed(payload: dict) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, json.dumps(payload), "")

    @patch("worker.services.media_service.subprocess.run")
    def test_normalizes_browser_motion_for_decord(self, run) -> None:
        destination = Path("motion.normalized.mp4")
        with patch.object(Path, "is_file", return_value=True), patch.object(
            Path, "stat"
        ) as stat:
            stat.return_value.st_size = 100
            self.service.normalize_motion(self.path, destination)

        command = run.call_args.args[0]
        self.assertEqual(command[0], "ffmpeg")
        self.assertIn("+genpts", command)
        self.assertIn("libx264", command)
        self.assertIn("yuv420p", command)
        self.assertEqual(command[-1], str(destination))
        self.assertEqual(run.call_args.kwargs["timeout"], 120)

    @patch("worker.services.media_service.subprocess.run")
    def test_maps_normalization_failure_to_typed_error(self, run) -> None:
        run.side_effect = subprocess.CalledProcessError(1, ["ffmpeg"])

        with self.assertRaisesRegex(WorkerError, "MOTION_INVALID"):
            self.service.normalize_motion(
                self.path, Path("motion.normalized.mp4")
            )

    @patch("worker.services.media_service.subprocess.run")
    def test_accepts_decodable_portrait(self, run) -> None:
        run.return_value = self.completed(
            {"streams": [{"codec_type": "video", "width": 750, "height": 1068}]}
        )

        self.service.probe_portrait(self.path)

    @patch("worker.services.media_service.subprocess.run")
    def test_accepts_motion_with_supported_duration(self, run) -> None:
        run.return_value = self.completed(
            {
                "format": {"duration": "15.000"},
                "streams": [{"codec_type": "video", "width": 720, "height": 1280}],
            }
        )

        self.service.probe_motion(self.path, 5000, 15000)

    @patch("worker.services.media_service.subprocess.run")
    def test_rejects_motion_outside_supported_duration(self, run) -> None:
        run.return_value = self.completed(
            {
                "format": {"duration": "15.100"},
                "streams": [{"codec_type": "video", "width": 720, "height": 1280}],
            }
        )

        with self.assertRaisesRegex(WorkerError, "MOTION_DURATION_INVALID"):
            self.service.probe_motion(self.path, 5000, 15000)

    @patch("worker.services.media_service.subprocess.run")
    def test_maps_ffprobe_failure_to_typed_error(self, run) -> None:
        run.side_effect = subprocess.CalledProcessError(1, ["ffprobe"])

        with self.assertRaisesRegex(WorkerError, "MOTION_INVALID"):
            self.service.probe_motion(self.path, 5000, 15000)


if __name__ == "__main__":
    unittest.main()
