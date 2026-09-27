import math
import os
from typing import Optional, List, Dict, Any

from src.common.models import Session, DirEntry
from src.common.exceptions import (
    PermissionDenied, QuotaExceeded, ENOENT, EEXIST, ENOTEMPTY, SimulatedCrashError
)
from src.m1_storage.allocator import GLOBAL_STORAGE, StorageEngine
from src.m2_security.auth import GLOBAL_AUTH, AuthManager
from src.m2_security.rbac import check_rbac
from src.m2_security.permissions import check_permission_bits
from src.m2_security.crypto import generate_key, encrypt_data, decrypt_data
from src.m2_security.audit import log_access_attempt
from src.m3_reliability.journal import GLOBAL_JOURNAL, JournalManager
from src.m3_reliability.cache import GLOBAL_CACHE, LRUCache
from src.m3_reliability.compression import compress_block, decompress_block
from src.m3_reliability.versioning import GLOBAL_VERSIONING, VersionStore
from src.m3_reliability.recovery import replay_journal
from src.m4_integration.quota import GLOBAL_QUOTA, QuotaManager
from src.common.event_bus import emit_metric

class FileSystemFacade:
    """
    Layer 3 Syscall Facade — The single funnel through which all file system requests pass.
    Strictly enforces pipeline ordering and isolation (architecture.md §9).
    """
    def __init__(
        self,
        storage: StorageEngine = GLOBAL_STORAGE,
        auth: AuthManager = GLOBAL_AUTH,
        journal: JournalManager = GLOBAL_JOURNAL,
        cache: LRUCache = GLOBAL_CACHE,
        versioning: VersionStore = GLOBAL_VERSIONING,
        quota: QuotaManager = GLOBAL_QUOTA
    ):
        self.storage = storage
        self.auth = auth
        self.journal = journal
        self.cache = cache
        self.versioning = versioning
        self.quota = quota

    def handle_boot(self, disk_path: str = "disk.img") -> Dict[str, Any]:
        """Boot sequence: mounts virtual disk image then executes Pipeline C crash recovery."""
        if os.path.exists(disk_path):
            self.storage.mount_disk(disk_path)
        else:
            self.storage.format_disk(disk_path, size_bytes=67108864, block_size=4096, mode="FAT")
        
        recovery_report = replay_journal(self.journal, self.storage)
        return recovery_report

    # --- PIPELINE A: WRITE OPERATION ---

    def handle_write_request(self, path: str, data: bytes, token: str, _fail_after: Optional[str] = None) -> int:
        """
        Executes Pipeline A Write Request:
        Auth -> RBAC/Perm -> Quota -> WAL Journal -> Compress -> Encrypt -> Allocate -> Write -> Cache -> Version -> WAL Commit -> Quota Update -> Metrics
        """
        # Step 1: Validate Session
        session = self.auth.validate_session(token)
        user = self.auth.get_user_by_id(session.uid)
        if not user:
            raise PermissionDenied("User not found")

        # Step 2: RBAC Check & Permission Bits Check
        if not check_rbac(user.role, "write", user.uid):
            log_access_attempt(user.uid, "write", path, "DENIED_RBAC")
            raise PermissionDenied(f"Role '{user.role}' is not authorized for write operations")

        entry = self.storage.resolve_path(path)
        if entry:
            if entry.entry_type != "file":
                raise PermissionDenied(f"Target '{path}' is a directory, not a file")
            if not check_permission_bits(entry.perm_bits, entry.owner_uid, user.uid, "w"):
                log_access_attempt(user.uid, "write", path, "DENIED_PERM_BITS")
                raise PermissionDenied(f"Permission denied for writing to file '{path}'")
        else:
            # File does not exist, create stub entry first
            entry = self.storage.create_file(path, owner_uid=user.uid, perm_bits=0o644)

        # Step 3: Quota Check
        incoming_len = len(data)
        if not self.quota.check_quota(user.uid, incoming_len):
            log_access_attempt(user.uid, "write", path, "DENIED_QUOTA")
            raise QuotaExceeded(f"Write of {incoming_len} bytes exceeds storage quota for user '{user.username}'")

        # Step 4: WAL Journal Intent Write (Flush to disk before touching real data!)
        old_blocks = self.storage.get_file_blocks(path)
        old_state = {"file_existed": bool(old_blocks), "blocks": old_blocks, "size": entry.size_bytes}
        new_state = {"path": path, "incoming_len": incoming_len}

        txn_id = self.journal.journal_write_intent("WRITE", path, old_state, new_state)

        # Crash Injection Hook 1
        if _fail_after == "journal":
            raise SimulatedCrashError("Simulated crash after writing journal intent record")

        # Step 5: Compression (zlib) BEFORE Encryption
        compressed_data = compress_block(data)

        # Step 6: Encryption (AES-GCM) AFTER Compression
        file_key = generate_key(user.uid, entry.target)
        encrypted_payload = encrypt_data(compressed_data, file_key)

        # Split encrypted payload into 4096-byte block chunks
        block_size = self.storage.superblock.block_size
        n_blocks = math.ceil(len(encrypted_payload) / block_size) if len(encrypted_payload) > 0 else 1
        payload_blocks = []
        for i in range(n_blocks):
            chunk = encrypted_payload[i * block_size : (i + 1) * block_size]
            payload_blocks.append(chunk)

        # Step 7: Block Allocation & Physical Write to Virtual Disk
        bytes_written = self.storage.write_file_blocks(path, payload_blocks)

        # Crash Injection Hook 2 & 3
        if _fail_after in ("allocate", "physical_write"):
            raise SimulatedCrashError(f"Simulated crash after {_fail_after}")

        # Step 8: LRU Cache Update
        new_blocks = self.storage.get_file_blocks(path)
        for idx, bid in enumerate(new_blocks):
            if idx < len(payload_blocks):
                self.cache.put(bid, payload_blocks[idx])

        # Step 9: Versioning Snapshot
        self.versioning.create_version(path, new_blocks)

        # Step 10: WAL Commit Record
        self.journal.journal_commit(txn_id)

        # Crash Injection Hook 4
        if _fail_after == "commit":
            raise SimulatedCrashError("Simulated crash after writing journal commit record")

        # Step 11: Quota Update
        self.quota.update_usage(user.uid, incoming_len - old_state["size"])

        # Step 12: Audit & Metrics
        log_access_attempt(user.uid, "write", path, "SUCCESS")
        emit_metric("file_written", {"path": path, "bytes": incoming_len, "uid": user.uid})
        return incoming_len

    # --- PIPELINE B: READ OPERATION ---

    def handle_read_request(self, path: str, token: str) -> bytes:
        """
        Executes Pipeline B Read Request:
        Auth -> RBAC/Perm -> Cache check (HIT -> decrypt+decompress) -> (MISS -> Disk read -> Decrypt -> Decompress -> Cache put) -> Metrics
        """
        # Step 1: Validate Session
        session = self.auth.validate_session(token)
        user = self.auth.get_user_by_id(session.uid)
        if not user:
            raise PermissionDenied("User not found")

        # Step 2: RBAC & Permission Bits Check
        if not check_rbac(user.role, "read", user.uid):
            log_access_attempt(user.uid, "read", path, "DENIED_RBAC")
            raise PermissionDenied(f"Role '{user.role}' is not authorized for read operations")

        entry = self.storage.resolve_path(path)
        if not entry or entry.entry_type != "file":
            log_access_attempt(user.uid, "read", path, "ENOENT")
            raise ENOENT(f"File not found: {path}")

        if not check_permission_bits(entry.perm_bits, entry.owner_uid, user.uid, "r"):
            log_access_attempt(user.uid, "read", path, "DENIED_PERM_BITS")
            raise PermissionDenied(f"Permission denied for reading file '{path}'")

        file_key = generate_key(user.uid, entry.target)

        # Step 3: Cache & Physical Block Read
        block_ids = self.storage.get_file_blocks(path)
        if not block_ids:
            log_access_attempt(user.uid, "read", path, "SUCCESS")
            return b""

        encrypted_payload = bytearray()
        for bid in block_ids:
            cached = self.cache.get(bid)
            if cached:
                encrypted_payload.extend(cached)
            else:
                raw_b = self.storage.disk.read_block(bid)
                self.cache.put(bid, raw_b)
                encrypted_payload.extend(raw_b)

        # Step 4: Decryption BEFORE Decompression
        compressed_data = decrypt_data(bytes(encrypted_payload[:entry.size_bytes if entry.size_bytes > 0 else len(encrypted_payload)]), file_key)

        # Step 5: Decompression
        plaintext = decompress_block(compressed_data)

        log_access_attempt(user.uid, "read", path, "SUCCESS")
        emit_metric("file_read", {"path": path, "bytes": len(plaintext), "uid": user.uid})
        return plaintext

    # --- DIRECTORY & DESTRUCTION OPERATIONS ---

    def handle_mkdir_request(self, path: str, token: str) -> None:
        session = self.auth.validate_session(token)
        user = self.auth.get_user_by_id(session.uid)
        if not user or not check_rbac(user.role, "mkdir", user.uid):
            raise PermissionDenied("Unauthorized to create directory")

        txn_id = self.journal.journal_write_intent("MKDIR", path, None, {"path": path})
        self.storage.mkdir(path, owner_uid=user.uid)
        self.journal.journal_commit(txn_id)
        log_access_attempt(user.uid, "mkdir", path, "SUCCESS")

    def handle_delete_request(self, path: str, token: str) -> None:
        session = self.auth.validate_session(token)
        user = self.auth.get_user_by_id(session.uid)
        if not user or not check_rbac(user.role, "delete", user.uid):
            raise PermissionDenied("Unauthorized to delete file")

        entry = self.storage.resolve_path(path)
        if not entry:
            raise ENOENT(f"File not found: {path}")

        if not check_permission_bits(entry.perm_bits, entry.owner_uid, user.uid, "w"):
            raise PermissionDenied("Permission denied to delete file")

        blocks = self.storage.get_file_blocks(path)
        # Invalidate cache for deleted blocks
        for b in blocks:
            self.cache.invalidate(b)

        txn_id = self.journal.journal_write_intent("DELETE", path, {"blocks": blocks, "size": entry.size_bytes}, None)
        self.storage.delete_file(path)
        self.journal.journal_commit(txn_id)

        self.quota.update_usage(user.uid, -entry.size_bytes)
        log_access_attempt(user.uid, "delete", path, "SUCCESS")

    def handle_list_request(self, path: str, token: str) -> List[DirEntry]:
        session = self.auth.validate_session(token)
        user = self.auth.get_user_by_id(session.uid)
        if not user or not check_rbac(user.role, "read", user.uid):
            raise PermissionDenied("Unauthorized to list directory")
        return self.storage.list_dir(path)

GLOBAL_FACADE = FileSystemFacade()
