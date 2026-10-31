"""Argon2id hashing + one-time recovery code (SPEC 21.3)."""
from __future__ import annotations

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_ph = PasswordHasher()  # Argon2id, random salt per hash
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

MIN_PASSWORD_LEN = 8
RESET_SENTINEL = "!reset-required"  # legacy account that must set a password


def hash_secret(value: str) -> str:
    return _ph.hash(value)


def verify_secret(stored_hash: str, value: str) -> bool:
    if not stored_hash or stored_hash == RESET_SENTINEL:
        return False
    try:
        return _ph.verify(stored_hash, value)
    except (VerificationError, InvalidHashError):
        return False


def generate_recovery_code() -> str:
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(20))
    return "-".join(raw[i:i + 5] for i in range(0, 20, 5))
