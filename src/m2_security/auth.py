import os
import hmac
import secrets
import hashlib
import time
import threading
from typing import Dict, Optional

from src.common.models import User, Session
from src.common.exceptions import EUSEREXISTS, EAUTHFAILED, ESESSIONEXPIRED, ESESSIONINVALID
from src.m2_security.audit import log_access_attempt

class AuthManager:
    """Manages user registration, authentication, and session handling."""
    def __init__(self):
        self.users: Dict[str, User] = {}          # username -> User
        self.users_by_id: Dict[int, User] = {}    # uid -> User
        self.sessions: Dict[str, Session] = {}    # token -> Session
        self._next_uid = 1000
        self._lock = threading.Lock()

        # Create default admin and standard users
        self._create_default_users()

    def _create_default_users(self):
        self._register_user_internal("admin", "admin123", "admin")
        self._register_user_internal("alice", "alice123", "standard")
        self._register_user_internal("bob", "bob123", "standard")
        self._register_user_internal("guest", "guest123", "guest")

    def _register_user_internal(self, username: str, password: str, role: str) -> User:
        salt = os.urandom(16)
        p_hash = self.hash_password(password, salt)
        uid = self._next_uid
        self._next_uid += 1
        user = User(uid=uid, username=username, password_hash=p_hash, salt=salt, role=role)
        self.users[username] = user
        self.users_by_id[uid] = user
        return user

    def hash_password(self, password: str, salt: bytes) -> bytes:
        """PBKDF2 HMAC SHA-256 password hashing with per-user salt and 100,000 iterations."""
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)

    def verify_password(self, password: str, stored_hash: bytes, salt: bytes) -> bool:
        computed = self.hash_password(password, salt)
        return hmac.compare_digest(computed, stored_hash)

    def register_user(self, username: str, password: str, role: str = "standard") -> User:
        with self._lock:
            if username in self.users:
                raise EUSEREXISTS(f"Username '{username}' is already taken.")
            return self._register_user_internal(username, password, role)

    def authenticate(self, username: str, password: str) -> Session:
        with self._lock:
            user = self.users.get(username)
            dummy_salt = b"0" * 16
            dummy_hash = b"0" * 32

            if user:
                valid = self.verify_password(password, user.password_hash, user.salt)
            else:
                # Perform dummy verification to prevent timing side-channel attacks
                self.verify_password(password, dummy_hash, dummy_salt)
                valid = False

            if not valid or not user:
                log_access_attempt(uid=0, op="login", target=username, result="FAILED")
                # Generic authentication failure message (prevents username enumeration)
                raise EAUTHFAILED("Invalid credentials")

            session = self.create_session(user.uid)
            log_access_attempt(uid=user.uid, op="login", target=username, result="SUCCESS")
            return session

    def create_session(self, uid: int, timeout_sec: int = 1800) -> Session:
        token = secrets.token_urlsafe(32)
        now = time.time()
        session = Session(token=token, uid=uid, created_at=now, expires_at=now + timeout_sec)
        self.sessions[token] = session
        return session

    def validate_session(self, token: str) -> Session:
        with self._lock:
            if not token or token not in self.sessions:
                raise ESESSIONINVALID("Session token invalid or missing")
            session = self.sessions[token]
            if time.time() > session.expires_at:
                del self.sessions[token]
                raise ESESSIONEXPIRED("Session token has expired")
            return session

    def revoke_session(self, token: str) -> None:
        with self._lock:
            if token in self.sessions:
                del self.sessions[token]

    def get_user_by_id(self, uid: int) -> Optional[User]:
        return self.users_by_id.get(uid)

GLOBAL_AUTH = AuthManager()
