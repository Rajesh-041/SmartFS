import os
import hashlib
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from src.common.exceptions import EDECRYPTFAILED

_MASTER_KEYS = {}  # uid -> master_key (session held)

def register_master_key(uid: int, master_key: bytes) -> None:
    _MASTER_KEYS[uid] = master_key

def generate_key(uid: int, file_id: int, master_key: Optional[bytes] = None) -> bytes:
    """Derives a per-file 256-bit key using HKDF-style PBKDF2 derivation."""
    if master_key is None:
        master_key = _MASTER_KEYS.get(uid, b"smartfs_default_master_key_32b!")
    salt = f"file_{file_id}".encode("utf-8")
    return hashlib.pbkdf2_hmac("sha256", master_key, salt, 10000, 32)

def encrypt_data(data: bytes, key: bytes) -> bytes:
    """Encrypts data using AES-256-GCM authenticated cipher."""
    if len(key) != 32:
        key = hashlib.sha256(key).digest()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    return nonce + ciphertext

def decrypt_data(payload: bytes, key: bytes) -> bytes:
    """Decrypts AES-256-GCM ciphertext. Raises EDECRYPTFAILED on auth tag mismatch."""
    if len(payload) < 12:
        raise EDECRYPTFAILED("Ciphertext payload too short")
    if len(key) != 32:
        key = hashlib.sha256(key).digest()
    nonce = payload[:12]
    ciphertext = payload[12:]
    aesgcm = AESGCM(key)
    try:
        return aesgcm.decrypt(nonce, ciphertext, None)
    except Exception as e:
        raise EDECRYPTFAILED(f"Decryption failed or data tampered: {e}")

def rotate_key(uid: int) -> None:
    """Rotates master key for a user."""
    _MASTER_KEYS[uid] = os.urandom(32)
