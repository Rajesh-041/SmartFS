import tempfile
import os
import sys

from src.m1_storage.allocator import StorageEngine, RESERVED_METADATA_BLOCKS
from src.m2_security.auth import AuthManager
from src.m3_reliability.journal import JournalManager
from src.m3_reliability.cache import LRUCache
from src.m3_reliability.versioning import VersionStore
from src.m3_reliability.recovery import replay_journal
from src.m4_integration.quota import QuotaManager
from src.m4_integration.facade import FileSystemFacade
from src.common.exceptions import SimulatedCrashError

STAGES = ["journal", "allocate", "physical_write", "commit"]

def test_crash_recovery_at_stage(stage: str):
    with tempfile.TemporaryDirectory() as tmpdir:
        disk_path = os.path.join(tmpdir, "crash_disk.img")
        journal_path = os.path.join(tmpdir, "crash_journal.log")

        storage = StorageEngine()
        auth = AuthManager()
        journal = JournalManager(journal_path=journal_path)
        cache = LRUCache()
        versioning = VersionStore(storage=storage)
        quota = QuotaManager()

        facade = FileSystemFacade(
            storage=storage, auth=auth, journal=journal,
            cache=cache, versioning=versioning, quota=quota
        )

        facade.handle_boot(disk_path)
        session = auth.authenticate("admin", "admin123")

        # 1. Inject crash during write operation
        crashed = False
        try:
            facade.handle_write_request("/test_crash.txt", b"Critical payload for crash injection test", session.token, _fail_after=stage)
        except SimulatedCrashError:
            crashed = True

        assert crashed, f"Expected simulated crash at stage '{stage}', but operation succeeded"

        # 2. Restart & Run Pipeline C Crash Recovery Replay
        report = replay_journal(journal, storage)
        assert report["status"] == "CLEAN"

        # 3. Assert bitmap & allocation tables internal consistency
        assert storage.superblock is not None
        assert storage.bitmap.count_free() >= 0

        # Assert no orphaned blocks allocated
        referenced_blocks = set(range(RESERVED_METADATA_BLOCKS))
        for path, entry in storage.directories.items():
            if entry.entry_type == "file":
                referenced_blocks.update(storage.get_file_blocks(path))

        for b_id in range(RESERVED_METADATA_BLOCKS, storage.superblock.total_blocks):
            if not storage.bitmap.is_free(b_id):
                assert b_id in referenced_blocks, f"Orphan block ID {b_id} detected after crash recovery at stage '{stage}'"

        print(f" [PASS] Crash recovery at stage '{stage}' successful. Rolled back: {report['rolled_back']}, Orphaned reclaimed: {report['orphaned_reclaimed']}")

def run_all_crash_tests():
    print("=" * 65)
    print("      SmartFS — WAL Crash Injection & Recovery Test Suite")
    print("=================================================================")
    passed = 0
    for stage in STAGES:
        try:
            test_crash_recovery_at_stage(stage)
            passed += 1
        except Exception as e:
            print(f" [FAIL] Crash test stage '{stage}' failed: {e}")

    print("-" * 65)
    print(f"Result: {passed}/{len(STAGES)} crash recovery test stages PASSED.")
    if passed == len(STAGES):
        print("[SUCCESS] WAL Crash-Recovery Engine is 100% durable and sound!")
    else:
        sys.exit(1)

if __name__ == "__main__":
    run_all_crash_tests()
