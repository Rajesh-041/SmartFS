import time
from typing import List, Dict, Any
from src.common.event_bus import emit_metric

_AUDIT_LOG: List[Dict[str, Any]] = []

def log_access_attempt(uid: int, op: str, target: str, result: str) -> None:
    """Logs security access attempts and emits audit metric."""
    entry = {
        "uid": uid,
        "op": op,
        "target": target,
        "result": result,
        "timestamp": time.time()
    }
    _AUDIT_LOG.append(entry)
    emit_metric("access_logged", entry)

def get_audit_log() -> List[Dict[str, Any]]:
    return list(_AUDIT_LOG)
