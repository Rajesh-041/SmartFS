import pytest
from src.m2_security.auth import AuthManager
from src.m2_security.rbac import check_rbac
from src.m2_security.permissions import check_permission_bits
from src.m2_security.crypto import generate_key, encrypt_data, decrypt_data
from src.common.exceptions import EUSEREXISTS, EAUTHFAILED, EDECRYPTFAILED

def test_m2_authentication():
    auth = AuthManager()
    user = auth.register_user("testuser", "secret123", "standard")
    assert user.username == "testuser"

    with pytest.raises(EUSEREXISTS):
        auth.register_user("testuser", "anotherpass", "standard")

    # Success login
    session = auth.authenticate("testuser", "secret123")
    assert session.uid == user.uid

    # Failure login — generic EAUTHFAILED
    with pytest.raises(EAUTHFAILED):
        auth.authenticate("testuser", "wrongpass")

    with pytest.raises(EAUTHFAILED):
        auth.authenticate("nonexistent", "secret123")

def test_m2_rbac_matrix():
    assert check_rbac("admin", "admin") is True
    assert check_rbac("admin", "write") is True
    assert check_rbac("standard", "write") is True
    assert check_rbac("standard", "admin") is False
    assert check_rbac("guest", "read") is True
    assert check_rbac("guest", "write") is False

def test_m2_permission_bits():
    # 0o755 = rwxr-xr-x (owner=7, group=5, other=5)
    perm = 0o755
    owner_uid = 1000
    other_uid = 2000

    assert check_permission_bits(perm, owner_uid, owner_uid, "r") is True
    assert check_permission_bits(perm, owner_uid, owner_uid, "w") is True
    assert check_permission_bits(perm, owner_uid, owner_uid, "x") is True

    assert check_permission_bits(perm, owner_uid, other_uid, "r") is True
    assert check_permission_bits(perm, owner_uid, other_uid, "w") is False
    assert check_permission_bits(perm, owner_uid, other_uid, "x") is True

def test_m2_crypto_roundtrip_and_tamper():
    key = generate_key(1001, 42, master_key=b"secret_master_key_32bytes_long!")
    plaintext = b"Sensitivestorage payload for SmartFS testing"

    ciphertext = encrypt_data(plaintext, key)
    assert ciphertext != plaintext

    decrypted = decrypt_data(ciphertext, key)
    assert decrypted == plaintext

    # Tamper ciphertext -> EDECRYPTFAILED
    tampered = bytearray(ciphertext)
    tampered[-1] ^= 0xFF
    with pytest.raises(EDECRYPTFAILED):
        decrypt_data(bytes(tampered), key)
