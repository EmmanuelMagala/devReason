"""Encryption for server-side OAuth credentials. Never return these to clients."""
import base64
import hashlib
from cryptography.fernet import Fernet
from src.core.settings import settings


def cipher() -> Fernet:
    try: raw=bytes.fromhex(settings.encryption_key)
    except ValueError: raise ValueError('ENCRYPTION_KEY must contain hexadecimal bytes') from None
    if len(raw)==16:
        # Earlier setup instructions provided 16-byte keys; Fernet needs 32.
        raw=hashlib.sha256(b'devreason:fernet:v1:'+raw).digest()
    if len(raw)!=32: raise ValueError('ENCRYPTION_KEY must contain 32 or 64 hexadecimal characters')
    return Fernet(base64.urlsafe_b64encode(raw))


def encrypt(value: str) -> str:
    return cipher().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    return cipher().decrypt(value.encode()).decode()
