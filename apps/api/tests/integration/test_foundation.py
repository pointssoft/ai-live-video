import hashlib
import uuid
from io import BytesIO

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.tasks.media_validation import process_one

ORIGIN = "http://localhost:3000"


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def csrf(client: TestClient) -> str:
    response = client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    return response.json()["csrf_token"]


def register(client: TestClient) -> dict[str, str]:
    email = f"integration-{uuid.uuid4()}@example.com"
    token = csrf(client)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct horse battery staple"},
        headers={"X-CSRF-Token": token, "Origin": ORIGIN},
    )
    assert response.status_code == 201, response.text
    assert client.cookies.get("mm_session")
    return response.json()["user"]


def test_health_and_auth_lifecycle(client: TestClient) -> None:
    client.cookies.clear()
    assert client.get("/health/live").status_code == 200
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"

    user = register(client)
    me = client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["id"] == user["id"]

    token = csrf(client)
    logout = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": token, "Origin": ORIGIN},
    )
    assert logout.status_code == 204
    assert client.get("/api/v1/me").status_code == 401


def test_direct_upload_and_ownership(client: TestClient) -> None:
    client.cookies.clear()
    image = Image.new("RGB", (512, 640), color=(30, 80, 140))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    content = buffer.getvalue()
    digest = hashlib.sha256(content).hexdigest()

    register(client)
    token = csrf(client)
    wrong_kind = client.post(
        "/api/v1/uploads",
        json={
            "kind": "PORTRAIT_ORIGINAL",
            "content_type": "video/mp4",
            "size_bytes": len(content),
            "sha256": digest,
        },
        headers={"X-CSRF-Token": token, "Origin": ORIGIN},
    )
    assert wrong_kind.status_code == 422

    created = client.post(
        "/api/v1/uploads",
        json={
            "kind": "PORTRAIT_ORIGINAL",
            "content_type": "image/jpeg",
            "size_bytes": len(content),
            "sha256": digest,
        },
        headers={"X-CSRF-Token": token, "Origin": ORIGIN},
    )
    assert created.status_code == 201, created.text
    upload = created.json()

    stored = httpx.put(upload["upload_url"], content=content, headers=upload["required_headers"])
    assert stored.status_code == 200, stored.text

    completed = client.post(
        f"/api/v1/uploads/{upload['upload_id']}/complete",
        headers={"X-CSRF-Token": token, "Origin": ORIGIN},
    )
    assert completed.status_code == 202, completed.text
    assert completed.json()["state"] == "UPLOADED"

    assert client.portal is not None
    client.portal.call(process_one, None, uuid.UUID(upload["upload_id"]))
    validated = client.get(f"/api/v1/uploads/{upload['upload_id']}")
    assert validated.status_code == 200
    assert validated.json()["state"] == "READY"
    assert validated.json()["detected_content_type"] == "image/jpeg"
    assert validated.json()["width"] == 512
    assert validated.json()["height"] == 640

    portrait_created = client.post(
        "/api/v1/portraits",
        json={"original_asset_id": upload["upload_id"]},
        headers={"X-CSRF-Token": token, "Origin": ORIGIN},
    )
    assert portrait_created.status_code == 201, portrait_created.text
    portrait = portrait_created.json()
    assert "object_key" not in portrait
    assert httpx.get(portrait["image_url"]).status_code == 200

    replay = client.post(
        "/api/v1/portraits",
        json={"original_asset_id": upload["upload_id"]},
        headers={"X-CSRF-Token": token, "Origin": ORIGIN},
    )
    assert replay.status_code == 200
    assert replay.json()["id"] == portrait["id"]
    library = client.get("/api/v1/portraits?limit=1")
    assert library.status_code == 200
    assert library.json()["items"][0]["id"] == portrait["id"]
    assert client.get(f"/api/v1/portraits/{portrait['id']}").status_code == 200

    deleted = client.delete(
        f"/api/v1/portraits/{portrait['id']}",
        headers={"X-CSRF-Token": token, "Origin": ORIGIN},
    )
    assert deleted.status_code == 204
    repeated_delete = client.delete(
        f"/api/v1/portraits/{portrait['id']}",
        headers={"X-CSRF-Token": token, "Origin": ORIGIN},
    )
    assert repeated_delete.status_code == 204
    assert client.get(f"/api/v1/portraits/{portrait['id']}").status_code == 404

    client.cookies.clear()
    register(client)
    hidden = client.get(f"/api/v1/uploads/{upload['upload_id']}")
    assert hidden.status_code == 404


def test_invalid_portrait_reaches_validation_failed(client: TestClient) -> None:
    client.cookies.clear()
    register(client)
    content = b"\xff\xd8\xffnot-a-decodable-image"
    digest = hashlib.sha256(content).hexdigest()
    token = csrf(client)
    created = client.post(
        "/api/v1/uploads",
        json={
            "kind": "PORTRAIT_ORIGINAL",
            "content_type": "image/jpeg",
            "size_bytes": len(content),
            "sha256": digest,
        },
        headers={"X-CSRF-Token": token, "Origin": ORIGIN},
    )
    upload = created.json()
    stored = httpx.put(upload["upload_url"], content=content, headers=upload["required_headers"])
    assert stored.status_code == 200
    completed = client.post(
        f"/api/v1/uploads/{upload['upload_id']}/complete",
        headers={"X-CSRF-Token": token, "Origin": ORIGIN},
    )
    assert completed.status_code == 202
    assert client.portal is not None
    client.portal.call(process_one, None, uuid.UUID(upload["upload_id"]))
    failed = client.get(f"/api/v1/uploads/{upload['upload_id']}")
    assert failed.json()["state"] == "VALIDATION_FAILED"
    assert failed.json()["validation_error_code"] == "PORTRAIT_INVALID"
