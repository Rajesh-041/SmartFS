from src.common.models import Session
from src.common.event_bus import emit_metric

RBAC_MATRIX = {
    "admin": {
        "read": True,
        "write": True,
        "delete": True,
        "mkdir": True,
        "rmdir": True,
        "admin": True,
    },
    "standard": {
        "read": True,
        "write": True,
        "delete": True,
        "mkdir": True,
        "rmdir": True,
        "admin": False,
    },
    "guest": {
        "read": True,
        "write": False,
        "delete": False,
        "mkdir": False,
        "rmdir": False,
        "admin": False,
    }
}

def check_rbac(role: str, operation: str, uid: int = 0) -> bool:
    """Checks role against RBAC matrix for operation class."""
    role_rules = RBAC_MATRIX.get(role.lower(), RBAC_MATRIX["guest"])
    allowed = role_rules.get(operation.lower(), False)

    emit_metric("rbac_checked", {
        "uid": uid,
        "role": role,
        "operation": operation,
        "allowed": allowed
    })
    return allowed
