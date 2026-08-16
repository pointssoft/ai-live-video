import uuid
from datetime import UTC, datetime

import pytest

from app.core.errors import ApiError
from app.models import Portrait
from app.services.portrait_service import decode_cursor, encode_cursor


def test_portrait_cursor_round_trip() -> None:
    portrait = Portrait(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        original_asset_id=uuid.uuid4(),
        status="READY",
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
        updated_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    assert decode_cursor(encode_cursor(portrait)) == (portrait.created_at, portrait.id)


def test_invalid_portrait_cursor_is_rejected() -> None:
    with pytest.raises(ApiError) as caught:
        decode_cursor("not-a-valid-cursor")
    assert caught.value.code == "INVALID_CURSOR"
