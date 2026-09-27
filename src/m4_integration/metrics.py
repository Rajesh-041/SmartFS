import threading
from typing import Dict, List, Any
from src.common.event_bus import subscribe

class MetricsCollector:
    """Listens to all system events and aggregates real-time metrics for the Layer 6 Dashboard."""
    def __init__(self):
        self._lock = threading.Lock()
        self.disk_usage = {"used_blocks": 16, "free_blocks": 16368, "total_blocks": 16384, "block_size": 4096}
        self.fragmentation_pct: float = 0.0
        self.cache_hit_ratio: float = 0.0
        self.quotas: Dict[int, Dict[str, Any]] = {}
        self.access_logs: List[Dict[str, Any]] = []
        self.journal_events: List[Dict[str, Any]] = []
        self.recovery_events: List[Dict[str, Any]] = []

        # Subscribe to all events
        subscribe("*", self._on_event)

    def _on_event(self, event: Dict[str, Any]) -> None:
        with self._lock:
            e_type = event.get("event_type")

            if e_type == "disk_usage_changed":
                self.disk_usage.update({
                    "used_blocks": event.get("used_blocks", self.disk_usage["used_blocks"]),
                    "free_blocks": event.get("free_blocks", self.disk_usage["free_blocks"]),
                    "total_blocks": event.get("total_blocks", self.disk_usage["total_blocks"]),
                })

            elif e_type in ("fragmentation_reported", "defrag_completed"):
                self.fragmentation_pct = event.get("fragmentation_pct", event.get("new_fragmentation_pct", self.fragmentation_pct))

            elif e_type in ("cache_hit", "cache_miss"):
                self.cache_hit_ratio = event.get("hit_ratio", self.cache_hit_ratio)

            elif e_type == "quota_updated":
                uid = event.get("uid")
                if uid is not None:
                    self.quotas[uid] = {
                        "uid": uid,
                        "used_bytes": event.get("used_bytes", 0),
                        "limit_bytes": event.get("limit_bytes", 10485760)
                    }

            elif e_type == "access_logged":
                self.access_logs.insert(0, event)
                if len(self.access_logs) > 50:
                    self.access_logs.pop()

            elif e_type == "journal_event":
                self.journal_events.insert(0, event)
                if len(self.journal_events) > 50:
                    self.journal_events.pop()

            elif e_type == "recovery_completed":
                self.recovery_events.insert(0, event)
                if len(self.recovery_events) > 10:
                    self.recovery_events.pop()

    def get_dashboard_data(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "disk_usage": dict(self.disk_usage),
                "fragmentation_pct": self.fragmentation_pct,
                "cache_hit_ratio": self.cache_hit_ratio,
                "quotas": list(self.quotas.values()),
                "access_logs": list(self.access_logs[:20]),
                "journal_events": list(self.journal_events[:20]),
                "recovery_events": list(self.recovery_events[:5]),
            }

GLOBAL_METRICS = MetricsCollector()
