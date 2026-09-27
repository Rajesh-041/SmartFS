import threading
from typing import Dict, Optional
from src.common.models import QuotaRecord
from src.common.exceptions import QuotaExceeded
from src.common.event_bus import emit_metric

DEFAULT_QUOTA_BYTES = 10485760  # 10 MB default quota per user

class QuotaManager:
    """Manages storage quotas on a per-user basis."""
    def __init__(self, default_limit: int = DEFAULT_QUOTA_BYTES):
        self.default_limit = default_limit
        self.quotas: Dict[int, QuotaRecord] = {}  # uid -> QuotaRecord
        self._lock = threading.Lock()

    def get_quota(self, uid: int) -> QuotaRecord:
        with self._lock:
            if uid not in self.quotas:
                self.quotas[uid] = QuotaRecord(uid=uid, limit_bytes=self.default_limit, used_bytes=0)
            return self.quotas[uid]

    def set_quota(self, uid: int, limit_bytes: int) -> None:
        with self._lock:
            if uid not in self.quotas:
                self.quotas[uid] = QuotaRecord(uid=uid, limit_bytes=limit_bytes, used_bytes=0)
            else:
                self.quotas[uid].limit_bytes = limit_bytes
        emit_metric("quota_updated", {"uid": uid, "limit_bytes": limit_bytes, "used_bytes": self.quotas[uid].used_bytes})

    def check_quota(self, uid: int, incoming_bytes: int) -> bool:
        """Pure check: returns True if allowed, False if would exceed."""
        rec = self.get_quota(uid)
        return not rec.would_exceed(incoming_bytes)

    def update_usage(self, uid: int, delta_bytes: int) -> None:
        with self._lock:
            rec = self.get_quota(uid)
            rec.used_bytes = max(0, rec.used_bytes + delta_bytes)

        emit_metric("quota_updated", {
            "uid": uid,
            "used_bytes": rec.used_bytes,
            "limit_bytes": rec.limit_bytes
        })

GLOBAL_QUOTA = QuotaManager()
