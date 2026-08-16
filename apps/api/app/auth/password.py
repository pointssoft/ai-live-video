from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> tuple[bool, str | None]:
    try:
        valid = _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False, None
    if valid and _hasher.check_needs_rehash(password_hash):
        return True, _hasher.hash(password)
    return valid, None
