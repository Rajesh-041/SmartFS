import json
import os
import time
import threading
from typing import List, Optional, Dict, Any

from src.common.models import JournalRecord, JournalStatus
from src.common.event_bus import emit_metric

JOURNAL_FILE_PATH = "journal.log"

class JournalManager:
    """Write-Ahead Logging (WAL) journal manager enforcing durable pre-commit flushes."""
    def __init__(self, journal_path: str = JOURNAL_FILE_PATH):
        self.journal_path = journal_path
        self._next_txn_id = 1
        self._lock = threading.Lock()
        self._init_journal()

    def _init_journal(self):
        with self._lock:
            records = self._read_all_unlocked()
            if records:
                self._next_txn_id = max(r.txn_id for r in records) + 1
            else:
                self._next_txn_id = 1

    def _read_all_unlocked(self) -> List[JournalRecord]:
        if not os.path.exists(self.journal_path):
            return []
        records = []
        with open(self.journal_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        records.append(JournalRecord.from_dict(data))
                    except Exception:
                        continue
        return records

    def journal_write_intent(self, op_type: str, target: str, old_state: Optional[Dict[str, Any]] = None, new_state: Optional[Dict[str, Any]] = None) -> int:
        """Writes a PENDING journal intent record and durably flushes to disk BEFORE returning."""
        with self._lock:
            txn_id = self._next_txn_id
            self._next_txn_id += 1
            record = JournalRecord(
                txn_id=txn_id,
                op_type=op_type,
                target=target,
                old_state=old_state,
                new_state=new_state,
                status=JournalStatus.PENDING,
                timestamp=time.time()
            )
            self._append_and_sync(record)

        emit_metric("journal_event", {
            "txn_id": txn_id,
            "op_type": op_type,
            "target": target,
            "status": "PENDING"
        })
        return txn_id

    def journal_commit(self, txn_id: int) -> None:
        """Appends COMMITTED status transition record and durably flushes."""
        with self._lock:
            record = JournalRecord(
                txn_id=txn_id,
                op_type="COMMIT",
                target=f"txn_{txn_id}",
                status=JournalStatus.COMMITTED,
                timestamp=time.time()
            )
            self._append_and_sync(record)

        emit_metric("journal_event", {
            "txn_id": txn_id,
            "op_type": "COMMIT",
            "target": f"txn_{txn_id}",
            "status": "COMMITTED"
        })

    def journal_rollback(self, txn_id: int) -> None:
        """Appends ROLLED_BACK status transition record and durably flushes."""
        with self._lock:
            record = JournalRecord(
                txn_id=txn_id,
                op_type="ROLLBACK",
                target=f"txn_{txn_id}",
                status=JournalStatus.ROLLED_BACK,
                timestamp=time.time()
            )
            self._append_and_sync(record)

        emit_metric("journal_event", {
            "txn_id": txn_id,
            "op_type": "ROLLBACK",
            "target": f"txn_{txn_id}",
            "status": "ROLLED_BACK"
        })

    def _append_and_sync(self, record: JournalRecord) -> None:
        line = json.dumps(record.to_dict()) + "\n"
        with open(self.journal_path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())  # Synchronous durable disk flush!

    def scan_journal(self) -> List[JournalRecord]:
        with self._lock:
            return self._read_all_unlocked()

    def clear(self) -> None:
        with self._lock:
            if os.path.exists(self.journal_path):
                os.remove(self.journal_path)
            self._next_txn_id = 1

GLOBAL_JOURNAL = JournalManager()
