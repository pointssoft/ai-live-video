import json

from livekit import api

from app.api.v1.realtime_sessions import create_participant_token


def test_realtime_token_is_scoped_to_room() -> None:
    token = create_participant_token(
        api_key="test-key",
        api_secret="s" * 32,
        room_name="realtime-test",
        identity="user-test",
        metadata=json.dumps({"portrait_id": "portrait-test"}),
        ttl_seconds=300,
    )

    claims = api.TokenVerifier("test-key", "s" * 32).verify(token)

    assert claims.identity == "user-test"
    assert claims.video is not None
    assert claims.video.room_join is True
    assert claims.video.room == "realtime-test"
    assert claims.video.can_publish is True
    assert claims.video.can_subscribe is True
    assert claims.video.can_publish_data is False
    assert json.loads(claims.metadata)["portrait_id"] == "portrait-test"
