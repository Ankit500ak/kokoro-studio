"""Fernet encryption for YouTube OAuth tokens."""

from cryptography.fernet import Fernet

from ..core.config import settings


def get_fernet() -> Fernet:
    """Return a Fernet instance from the configured encryption key."""
    key = settings.ENCRYPTION_KEY
    if not key:
        # ponytail: generate a key on first use and warn. Production should set ENCRYPTION_KEY.
        key = Fernet.generate_key().decode()
        settings.ENCRYPTION_KEY = key
        print(
            f"[WARNING] No ENCRYPTION_KEY set. Generated ephemeral key. Tokens will not survive restart."
        )
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


def encrypt_token(plaintext: str) -> str:
    """Encrypt a token string, returning a URL-safe base64-encoded string."""
    if not plaintext:
        return ""
    return get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """Decrypt an encrypted token string back to plaintext."""
    if not ciphertext:
        return ""
    return get_fernet().decrypt(ciphertext.encode()).decode()


def decrypt_token_or_raw(value: str) -> str:
    """Decrypt a stored secret, falling back to the raw value.

    Only for fields historically stored in plaintext (client_id / client_secret):
    the OAuth callback writes those with encrypt_token() never being applied, so
    strict decryption always raised InvalidToken. Access and refresh tokens must
    keep using decrypt_token() so key rotation problems surface loudly.
    """
    if not value:
        return ""
    try:
        return get_fernet().decrypt(value.encode()).decode()
    except Exception:
        return value
