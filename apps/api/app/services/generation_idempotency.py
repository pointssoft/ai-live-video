import hashlib
import json
import uuid


def generation_request_fingerprint(
    portrait_id: uuid.UUID,
    motion_asset_id: uuid.UUID,
    profile: str = "mimicmotion-v1.1-balanced-v1",
    seed: int = 42,
) -> str:
    canonical = json.dumps(
        {
            "motion_asset_id": str(motion_asset_id),
            "operation": "generation.create",
            "portrait_id": str(portrait_id),
            "profile": profile,
            "seed": seed,
            "version": 2,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def retry_request_fingerprint(generation_id: uuid.UUID) -> str:
    canonical = json.dumps(
        {
            "generation_id": str(generation_id),
            "operation": "generation.retry",
            "version": 1,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def validate_idempotency_key(value: str) -> str:
    if (
        not 1 <= len(value) <= 255
        or not value.isascii()
        or not value.isprintable()
        or any(character.isspace() for character in value)
    ):
        raise ValueError("IDEMPOTENCY_KEY_INVALID")
    return value
