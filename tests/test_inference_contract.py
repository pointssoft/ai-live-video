import unittest

from mimicmotion.utils.inference_contract import (
    InferenceContractError,
    pipeline_pose_kwargs,
    resolve_temporal_tiles,
    validate_pose_sequence,
)


class FakePose:
    def __init__(self, shape, floating=True):
        self.shape = shape
        self._floating = floating

    def is_floating_point(self):
        return self._floating


class InferenceContractTests(unittest.TestCase):
    def test_pipeline_kwargs_preserve_tchw_without_batch_dimension(self):
        pose = FakePose((5, 3, 8, 16))
        kwargs = pipeline_pose_kwargs(pose, requested_tile_size=72, tile_overlap=2)
        self.assertIs(kwargs["image_pose"], pose)
        self.assertEqual(kwargs["num_frames"], 5)
        self.assertEqual(kwargs["tile_size"], 5)
        self.assertEqual(kwargs["height"], 8)
        self.assertEqual(kwargs["width"], 16)

    def test_accidental_cog_batch_dimension_is_rejected(self):
        with self.assertRaisesRegex(InferenceContractError, r"\[T, 3, H, W\]"):
            validate_pose_sequence(
                FakePose((1, 5, 3, 8, 16)), num_frames=5, height=8, width=16
            )

    def test_temporal_tiles_preserve_reference_and_reach_later_frames(self):
        tile_size, indices = resolve_temporal_tiles(
            total_frames=10, requested_tile_size=5, tile_overlap=2
        )
        self.assertEqual(tile_size, 5)
        self.assertGreater(len(indices), 1)
        self.assertTrue(all(tile[0] == 0 for tile in indices))
        self.assertEqual(indices[-1][-1], 9)
        self.assertTrue(all(len(tile) == 5 for tile in indices))

    def test_short_clip_reduces_profile_tile_size(self):
        tile_size, indices = resolve_temporal_tiles(
            total_frames=61, requested_tile_size=72, tile_overlap=6
        )
        self.assertEqual(tile_size, 61)
        self.assertEqual(indices, [list(range(61))])

    def test_invalid_overlap_is_rejected_after_tile_reduction(self):
        for overlap in (-1, 8, 9):
            with self.subTest(overlap=overlap):
                with self.assertRaises(InferenceContractError):
                    resolve_temporal_tiles(
                        total_frames=8, requested_tile_size=72, tile_overlap=overlap
                    )

    def test_non_floating_pose_is_rejected(self):
        with self.assertRaisesRegex(InferenceContractError, "floating-point"):
            validate_pose_sequence(
                FakePose((5, 3, 8, 16), floating=False),
                num_frames=5,
                height=8,
                width=16,
            )


if __name__ == "__main__":
    unittest.main()
