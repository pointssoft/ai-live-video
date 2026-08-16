from app.auth.password import hash_password, verify_password


def test_password_hash_is_not_plaintext() -> None:
    password = "correct horse battery staple"
    password_hash = hash_password(password)
    assert password not in password_hash
    assert verify_password(password_hash, password)[0] is True
    assert verify_password(password_hash, "wrong password")[0] is False
