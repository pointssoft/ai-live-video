from app.schemas.uploads import UploadCreate, UploadKind


def test_upload_schema_rejects_path_input_by_not_accepting_it() -> None:
    payload = UploadCreate(
        kind=UploadKind.PORTRAIT_ORIGINAL,
        content_type="image/jpeg",
        size_bytes=12,
        sha256="a" * 64,
    )
    assert payload.model_dump().keys() == {"kind", "content_type", "size_bytes", "sha256"}
