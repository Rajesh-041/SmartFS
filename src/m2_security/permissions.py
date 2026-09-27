from typing import Union
from src.common.models import Inode, DirEntry, Session
from src.common.exceptions import PermissionDenied

def check_permission_bits(perm_bits: int, owner_uid: int, requesting_uid: int, mode: str) -> bool:
    """Unix-style 9-bit permission check for mode ∈ {'r', 'w', 'x'}."""
    if mode == "r":
        bit_mask = 0o4
    elif mode == "w":
        bit_mask = 0o2
    elif mode == "x":
        bit_mask = 0o1
    else:
        return False

    if requesting_uid == owner_uid:
        # Check owner triplet (bits 6..8)
        owner_bits = (perm_bits >> 6) & 0o7
        return bool(owner_bits & bit_mask)
    else:
        # Check world/others triplet (bits 0..2)
        other_bits = perm_bits & 0o7
        return bool(other_bits & bit_mask)
