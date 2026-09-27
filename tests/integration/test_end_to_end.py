import tempfile
import os
import pytest

from src.m1_storage.allocator import StorageEngine
from src.m2_security.auth import AuthManager
from src.m3_reliability.journal import JournalManager
from src.m3_reliability.cache import LRUCache
from src.m3_reliability.versioning import VersionStore
from src.m3_reliability.recovery import replay_journal
from src.m4_integration.quota import QuotaManager
from src.m4_integration.facade import FileSystemFacade
from src.common.exceptions import PermissionDenied, QuotaExceeded, SimulatedCrashError

def test_integration_full_pipeline_write_read_delete():
    with tempfile.TemporaryDirectory() as tmpdir:
        disk_path = os.path.join(tmpdir, "e2e_disk.img")
        journal_path = os.path.join(tmpdir, "e2e_journal.log")

        storage = StorageEngine()
        auth = AuthManager()
        journal = JournalManager(journal_path=journal_path)
        cache = LRUCache(capacity=32)
        versioning = VersionStore(storage=storage)
        quota = QuotaManager()

        facade = FileSystemFacade(
            storage=storage, auth=auth, journal=journal,
            cache=cache, versioning=versioning, quota=quota
        )

        # Boot
        facade.handle_boot(disk_path)

        # 1. Login Alice
        session_alice = auth.authenticate("alice", "alice123")

        # 2. Mkdir
        facade.handle_mkdir_request("/home/alice/projects", session_alice.token)

        # 3. Write File
        secret_content = b"SmartFS End-to-End Encrypted File Payload 12345"
        bytes_written = facade.handle_write_request("/home/alice/projects/notes.txt", secret_content, session_alice.token)
        assert bytes_written == len(secret_content)

        # 4. Read File Back
        readback = facade.handle_read_request("/home/alice/projects/notes.txt", session_alice.token)
        assert readback == secret_content

        # 5. Delete File
        facade.handle_delete_request("/home/alice/projects/notes.txt", session_alice.token)

def test_integration_quota_enforcement():
    with tempfile.TemporaryDirectory() as tmpdir:
        disk_path = os.path.join(tmpdir, "e2e_quota.img")
        journal_path = os.path.join(tmpdir, "e2e_quota_journal.log")

        storage = StorageEngine()
        auth = AuthManager()
        journal = JournalManager(journal_path=journal_path)
        cache = LRUCache()
        versioning = VersionStore(storage=storage)
        quota = QuotaManager(default_limit=100) # Small quota 100 bytes

        facade = FileSystemFacade(storage=storage, auth=auth, journal=journal, cache=cache, versioning=versioning, quota=quota)
        facade.handle_boot(disk_path)

        session = auth.authenticate("alice", "alice123")
        
        # Exceed quota
        with pytest.raises(QuotaExceeded):
            facade.handle_write_request("/huge.txt", b"A" * 500, session.token)

def test_integration_permission_denial():
    with tempfile.TemporaryDirectory() as tmpdir:
        disk_path = os.path.join(tmpdir, "e2e_perm.img")
        journal_path = os.path.join(tmpdir, "e2e_perm_journal.log")

        storage = StorageEngine()
        auth = AuthManager()
        journal = JournalManager(journal_path=journal_path)
        cache = LRUCache()
        versioning = VersionStore(storage=storage)
        quota = QuotaManager()

        facade = FileSystemFacade(storage=storage, auth=auth, journal=journal, cache=cache, versioning=versioning, quota=quota)
        facade.handle_boot(disk_path)

        s_guest = auth.authenticate("guest", "guest123")

        # Guest cannot write
        with pytest.raises(PermissionDenied):
            facade.handle_write_request("/guest_file.txt", b"data", s_guest.token)
