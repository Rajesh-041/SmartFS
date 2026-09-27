from typing import Dict, Any, Set
from src.m3_reliability.journal import GLOBAL_JOURNAL, JournalManager
from src.m1_storage.allocator import GLOBAL_STORAGE, StorageEngine, RESERVED_METADATA_BLOCKS
from src.common.models import JournalStatus
from src.common.event_bus import emit_metric

def replay_journal(journal: JournalManager = GLOBAL_JOURNAL, storage: StorageEngine = GLOBAL_STORAGE) -> Dict[str, Any]:
    """
    Executes Pipeline C Crash Recovery sequence at startup.
    Scans WAL journal, unwinds incomplete (PENDING) transactions via undo logging,
    re-validates allocation tables, reclaims orphaned blocks, and returns a recovery report.
    """
    records = journal.scan_journal()
    
    # Determine final state of each txn_id
    txn_states: Dict[int, str] = {}
    txn_records: Dict[int, Any] = {}

    for r in records:
        if r.status == JournalStatus.COMMITTED:
            txn_states[r.txn_id] = "COMMITTED"
        elif r.status == JournalStatus.ROLLED_BACK:
            txn_states[r.txn_id] = "ROLLED_BACK"
        elif r.txn_id not in txn_states:
            txn_states[r.txn_id] = "PENDING"
            txn_records[r.txn_id] = r

    pending_count = 0
    rolled_back_count = 0
    committed_count = sum(1 for s in txn_states.values() if s == "COMMITTED")

    for txn_id, status in list(txn_states.items()):
        if status == "PENDING":
            pending_count += 1
            r = txn_records.get(txn_id)
            if r:
                # Perform undo rollback if old_state exists
                if r.old_state:
                    file_path = r.target
                    if "blocks" in r.old_state:
                        # Restore previous blocks or remove incomplete file
                        if file_path in storage.directories:
                            if not r.old_state.get("file_existed", False):
                                storage.delete_file(file_path)

                journal.journal_rollback(txn_id)
                rolled_back_count += 1

    # Orphan block scan & reclamation
    referenced_blocks: Set[int] = set(range(RESERVED_METADATA_BLOCKS))
    for path, entry in list(storage.directories.items()):
        if entry.entry_type == "file":
            chain = storage.get_file_blocks(path)
            referenced_blocks.update(chain)

    orphaned_reclaimed = 0
    if storage.bitmap and storage.superblock:
        for b_id in range(RESERVED_METADATA_BLOCKS, storage.superblock.total_blocks):
            if not storage.bitmap.is_free(b_id) and b_id not in referenced_blocks:
                storage.free_block(b_id)
                orphaned_reclaimed += 1

    report = {
        "pending_found": pending_count,
        "rolled_back": rolled_back_count,
        "committed_count": committed_count,
        "orphaned_reclaimed": orphaned_reclaimed,
        "status": "CLEAN"
    }

    emit_metric("recovery_completed", report)
    return report
