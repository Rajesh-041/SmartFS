import tempfile
import os
from src.m3_reliability.journal import JournalManager
from src.m3_reliability.cache import LRUCache
from src.m3_reliability.compression import compress_block, decompress_block
from src.m3_reliability.versioning import VersionStore

def test_m3_journal_durability_and_flush():
    with tempfile.TemporaryDirectory() as tmpdir:
        j_path = os.path.join(tmpdir, "journal.log")
        jm = JournalManager(journal_path=j_path)

        txn_id = jm.journal_write_intent("WRITE", "/test.txt", None, {"data": "hello"})
        records = jm.scan_journal()
        assert len(records) == 1
        assert records[0].txn_id == txn_id
        assert records[0].status.value == "PENDING"

        jm.journal_commit(txn_id)
        records_after = jm.scan_journal()
        assert len(records_after) == 2
        assert records_after[1].status.value == "COMMITTED"

def test_m3_lru_cache_eviction_order():
    cache = LRUCache(capacity=3)
    cache.put(1, b"b1")
    cache.put(2, b"b2")
    cache.put(3, b"b3")

    # Hit block 1 -> moves to head
    assert cache.get(1) == b"b1"

    # Put block 4 -> capacity 3 exceeded -> evicts tail (block 2)
    cache.put(4, b"b4")

    assert cache.get(2) is None
    assert cache.get(1) == b"b1"
    assert cache.get(3) == b"b3"
    assert cache.get(4) == b"b4"

def test_m3_compression_roundtrip():
    payload = b"SmartFS repeating text block payload " * 100
    compressed = compress_block(payload)
    assert len(compressed) < len(payload)

    decompressed = decompress_block(compressed)
    assert decompressed == payload

def test_m3_versioning_snapshots():
    vs = VersionStore()
    v1 = vs.create_version("/notes.txt", [10, 11, 12])
    v2 = vs.create_version("/notes.txt", [13, 14, 15])

    history = vs.list_versions("/notes.txt")
    assert len(history) == 2
    assert history[0].version_id == v1.version_id
    assert history[1].version_id == v2.version_id
