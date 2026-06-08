import hashlib
import hmac
import json
import os

from cryptography.fernet import Fernet, InvalidToken


def generate_hash(payload: str, secret: str) -> str:
    """HMAC-SHA256 of payload string using secret. Returns hex digest."""
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def hash_request(data: dict, secret: str) -> str:
    """Canonicalize a dict to JSON (sorted keys, no spaces) then HMAC it."""
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return generate_hash(payload, secret)


# ─── Fernet symmetric encryption ──────────────────────────────────────────────

def _get_encryption_key() -> str:
    """Return ENCRYPTION_KEY, preferring Django settings over raw env var."""
    try:
        from django.conf import settings
        key = getattr(settings, "ENCRYPTION_KEY", "") or os.getenv("ENCRYPTION_KEY", "")
    except Exception:
        key = os.getenv("ENCRYPTION_KEY", "")
    if not key:
        raise ValueError(
            "ENCRYPTION_KEY is not set. "
            "Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return key


def _get_cipher() -> Fernet:
    """Return a Fernet instance keyed from ENCRYPTION_KEY."""
    return Fernet(_get_encryption_key().encode())


def encrypt(data: str) -> str:
    """Encrypt a plaintext string; returns a URL-safe token string."""
    return _get_cipher().encrypt(data.encode()).decode()


def decrypt(data: str) -> str:
    """Decrypt a Fernet token string; returns the original plaintext."""
    try:
        return _get_cipher().decrypt(data.encode()).decode()
    except InvalidToken as exc:
        raise ValueError(f"Decryption failed — token invalid or wrong key: {exc}") from exc


def encrypt_card(card: str) -> str:
    """Encrypt a normalised 16-digit card number string."""
    return encrypt(card)


def decrypt_card(enc: str) -> str:
    """Decrypt a Fernet-encrypted card number back to its 16-digit string."""
    return decrypt(enc)


def _search_token(plain: str) -> str:
    """HMAC-SHA256 of the plain card number keyed by ENCRYPTION_KEY.

    Used as a deterministic, non-reversible search index so ORM lookups
    work without storing plaintext in the database.
    """
    key = _get_encryption_key().encode()
    return hmac.new(key, plain.encode(), hashlib.sha256).hexdigest()
