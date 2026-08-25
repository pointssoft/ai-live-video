import torch

from realtime_worker.motion import MotionState, limit_stitching_delta


def _source_info() -> dict[str, torch.Tensor]:
    return {
        "kp": torch.tensor(
            [[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]]
        ),
        "exp": torch.zeros(1, 3, 3),
        "scale": torch.ones(1, 1),
        "t": torch.zeros(1, 3),
    }


def _driver_info(
    expression: float = 0.0,
    scale: float = 1.0,
    translation: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> dict[str, torch.Tensor]:
    return {
        "exp": torch.full((1, 3, 3), expression),
        "scale": torch.tensor([[scale]]),
        "t": torch.tensor([translation]),
    }


def test_neutral_frame_preserves_source_geometry() -> None:
    source = _source_info()
    state = MotionState()
    state.update(_driver_info(), torch.eye(3).unsqueeze(0))

    rotation, expression, scale, translation = state.target_motion(
        source, torch.eye(3).unsqueeze(0), source["kp"]
    )
    target = scale.unsqueeze(-1) * (source["kp"] @ rotation + expression) + translation.unsqueeze(-2)

    assert torch.allclose(rotation, torch.eye(3).unsqueeze(0), atol=1e-5)
    assert torch.allclose(target, source["kp"], atol=1e-5)


def test_expression_motion_uses_source_keypoints_as_basis() -> None:
    source = _source_info()
    state = MotionState()
    state.update(_driver_info(), torch.eye(3).unsqueeze(0))
    state.update(_driver_info(expression=0.2), torch.eye(3).unsqueeze(0))

    _, expression, scale, translation = state.target_motion(
        source, torch.eye(3).unsqueeze(0), source["kp"]
    )
    target = scale.unsqueeze(-1) * (source["kp"] + expression) + translation.unsqueeze(-2)

    assert torch.all(expression > 0)
    assert torch.allclose(target - source["kp"], expression, atol=1e-5)


def test_outlier_motion_is_bounded_before_rendering() -> None:
    source = _source_info()
    state = MotionState()
    state.update(_driver_info(), torch.eye(3).unsqueeze(0))
    state.update(
        _driver_info(expression=100.0, scale=10.0, translation=(100.0, -100.0, 100.0)),
        torch.tensor([[[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]]),
    )

    _, expression, scale, translation = state.target_motion(
        source, torch.eye(3).unsqueeze(0), source["kp"]
    )
    face_extent = torch.linalg.vector_norm(
        source["kp"].amax(dim=-2) - source["kp"].amin(dim=-2), dim=-1
    )
    expression_delta = torch.linalg.vector_norm(expression, dim=-1)

    assert torch.all(expression_delta <= face_extent[:, None] * 0.55 * 0.80 + 1e-5)
    assert torch.all(scale <= 1.03 + 1e-5)
    assert torch.all(scale >= 0.97 - 1e-5)
    assert torch.all(torch.abs(translation[..., 0]) <= face_extent * 0.50 * 0.35 + 1e-5)
    assert torch.all(torch.abs(translation[..., 1]) <= face_extent * 0.50 * 0.20 + 1e-5)
    assert torch.all(translation[..., 2] == 0)


def test_nonfinite_first_observation_is_not_used_as_neutral() -> None:
    state = MotionState()
    invalid = _driver_info()
    invalid["exp"][..., 0] = float("nan")

    assert not state.update(invalid, torch.eye(3).unsqueeze(0))
    assert not state.initialized
    assert state.update(_driver_info(expression=0.2), torch.eye(3).unsqueeze(0))
    assert state.initialized


def test_nonfinite_observation_does_not_corrupt_neutral_state() -> None:
    source = _source_info()
    state = MotionState()
    state.update(_driver_info(), torch.eye(3).unsqueeze(0))
    state.update(
        {
            "exp": torch.full((1, 3, 3), float("nan")),
            "scale": torch.tensor([[float("nan")]]),
            "t": torch.tensor([[float("nan"), 0.0, 0.0]]),
        },
        torch.full((1, 3, 3), float("nan")),
    )

    _, expression, scale, translation = state.target_motion(
        source, torch.eye(3).unsqueeze(0), source["kp"]
    )

    assert torch.isfinite(expression).all()
    assert torch.allclose(scale, source["scale"], atol=1e-5)
    assert torch.allclose(translation, source["t"], atol=1e-5)


def test_reset_discards_previous_driver_baseline() -> None:
    source = _source_info()
    state = MotionState()
    state.update(_driver_info(expression=0.2), torch.eye(3).unsqueeze(0))
    state.reset()
    state.update(_driver_info(expression=0.8), torch.eye(3).unsqueeze(0))

    _, expression, _, _ = state.target_motion(
        source, torch.eye(3).unsqueeze(0), source["kp"]
    )

    assert torch.allclose(expression, source["exp"], atol=1e-5)


def test_stitching_correction_is_limited_to_face_extent() -> None:
    source = _source_info()["kp"]
    target = source.clone()
    stitched = target + 100.0

    safe = limit_stitching_delta(source, target, stitched)
    correction = torch.linalg.vector_norm(safe - target, dim=-1)
    face_extent = torch.linalg.vector_norm(
        source.amax(dim=-2) - source.amin(dim=-2), dim=-1
    )

    assert torch.all(correction <= face_extent[:, None] * 0.20 + 1e-5)
