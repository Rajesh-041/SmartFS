import json
import struct
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

FAT_EOF = -1
FAT_FREE = 0
MAGIC_BYTES = b"SMFS"
DIRECT_LIMIT = 12

@dataclass
class Superblock:
    magic: bytes = MAGIC_BYTES
    disk_size: int = 67108864
    block_size: int = 4096
    total_blocks: int = 16384
    free_blocks: int = 16384
    allocation_mode: str = "FAT"  # "FAT" or "INODE"
    root_dir_ptr: int = 0
    fs_version: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "magic": self.magic.decode('latin1'),
            "disk_size": self.disk_size,
            "block_size": self.block_size,
            "total_blocks": self.total_blocks,
            "free_blocks": self.free_blocks,
            "allocation_mode": self.allocation_mode,
            "root_dir_ptr": self.root_dir_ptr,
            "fs_version": self.fs_version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Superblock":
        return cls(
            magic=data["magic"].encode('latin1'),
            disk_size=data["disk_size"],
            block_size=data["block_size"],
            total_blocks=data["total_blocks"],
            free_blocks=data["free_blocks"],
            allocation_mode=data["allocation_mode"],
            root_dir_ptr=data["root_dir_ptr"],
            fs_version=data["fs_version"],
        )

class FreeBitmap:
    def __init__(self, total_blocks: int, bits: Optional[bytearray] = None):
        self.total_blocks = total_blocks
        num_bytes = (total_blocks + 7) // 8
        if bits is None:
            self.bits = bytearray(num_bytes)
        else:
            self.bits = bytearray(bits)

    def is_free(self, block_id: int) -> bool:
        if block_id < 0 or block_id >= self.total_blocks:
            return False
        byte_idx = block_id // 8
        bit_idx = block_id % 8
        return (self.bits[byte_idx] & (1 << bit_idx)) == 0

    def mark(self, block_id: int, allocated: bool) -> None:
        if block_id < 0 or block_id >= self.total_blocks:
            return
        byte_idx = block_id // 8
        bit_idx = block_id % 8
        if allocated:
            self.bits[byte_idx] |= (1 << bit_idx)
        else:
            self.bits[byte_idx] &= ~(1 << bit_idx)

    def find_free_run(self, n: int) -> Optional[List[int]]:
        """Contiguous-first search; falls back to scattered free blocks if no run exists."""
        run = []
        for i in range(self.total_blocks):
            if self.is_free(i):
                run.append(i)
                if len(run) == n:
                    return run
            else:
                run = []
        # Fallback to scattered free blocks
        scattered = []
        for i in range(self.total_blocks):
            if self.is_free(i):
                scattered.append(i)
                if len(scattered) == n:
                    return scattered
        return None

    def find_first_free(self) -> Optional[int]:
        for i in range(self.total_blocks):
            if self.is_free(i):
                return i
        return None

    def count_free(self) -> int:
        count = 0
        for i in range(self.total_blocks):
            if self.is_free(i):
                count += 1
        return count

class FatTable:
    def __init__(self, total_blocks: int, entries: Optional[List[int]] = None):
        self.total_blocks = total_blocks
        if entries is None:
            self.entries = [FAT_FREE] * total_blocks
        else:
            self.entries = list(entries)

    def chain(self, start: int) -> List[int]:
        """Walk entries from start until FAT_EOF."""
        result = []
        curr = start
        visited = set()
        while curr != FAT_EOF and curr != FAT_FREE:
            if curr in visited or curr < 0 or curr >= len(self.entries):
                break
            visited.add(curr)
            result.append(curr)
            curr = self.entries[curr]
        return result

    def link(self, prev: int, nxt: int) -> None:
        if 0 <= prev < len(self.entries):
            self.entries[prev] = nxt

    def free_chain(self, start: int) -> List[int]:
        freed = self.chain(start)
        for b in freed:
            if 0 <= b < len(self.entries):
                self.entries[b] = FAT_FREE
        return freed

@dataclass
class Inode:
    inode_id: int
    owner_uid: int = 0
    group_gid: int = 0
    perm_bits: int = 0o644
    size_bytes: int = 0
    ctime: float = field(default_factory=time.time)
    mtime: float = field(default_factory=time.time)
    direct_blocks: List[int] = field(default_factory=list)
    indirect_block: Optional[int] = None
    double_indirect: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "inode_id": self.inode_id,
            "owner_uid": self.owner_uid,
            "group_gid": self.group_gid,
            "perm_bits": self.perm_bits,
            "size_bytes": self.size_bytes,
            "ctime": self.ctime,
            "mtime": self.mtime,
            "direct_blocks": self.direct_blocks,
            "indirect_block": self.indirect_block,
            "double_indirect": self.double_indirect,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Inode":
        return cls(
            inode_id=d["inode_id"],
            owner_uid=d["owner_uid"],
            group_gid=d["group_gid"],
            perm_bits=d["perm_bits"],
            size_bytes=d["size_bytes"],
            ctime=d.get("ctime", time.time()),
            mtime=d.get("mtime", time.time()),
            direct_blocks=d.get("direct_blocks", []),
            indirect_block=d.get("indirect_block"),
            double_indirect=d.get("double_indirect"),
        )

class InodeTable:
    def __init__(self, inodes: Optional[Dict[int, Inode]] = None):
        self.inodes: Dict[int, Inode] = inodes if inodes is not None else {}
        self._next_id = max(self.inodes.keys(), default=0) + 1 if self.inodes else 1

    def allocate_inode(self, owner_uid: int = 0, group_gid: int = 0, perm_bits: int = 0o644) -> Inode:
        inode_id = self._next_id
        self._next_id += 1
        inode = Inode(inode_id=inode_id, owner_uid=owner_uid, group_gid=group_gid, perm_bits=perm_bits)
        self.inodes[inode_id] = inode
        return inode

    def free_inode(self, inode_id: int) -> List[int]:
        """Frees inode and returns all block ids it owned."""
        if inode_id not in self.inodes:
            return []
        inode = self.inodes.pop(inode_id)
        blocks = list(inode.direct_blocks)
        if inode.indirect_block is not None:
            blocks.append(inode.indirect_block)
        if inode.double_indirect is not None:
            blocks.append(inode.double_indirect)
        return blocks

@dataclass
class DirEntry:
    name: str
    entry_type: str        # "file" | "dir"
    target: int            # inode_id (INODE mode) or starting cluster (FAT mode)
    parent: int = 0        # parent directory's inode/cluster id
    size_bytes: int = 0
    mtime: float = field(default_factory=time.time)
    perm_bits: int = 0o755
    owner_uid: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "entry_type": self.entry_type,
            "target": self.target,
            "parent": self.parent,
            "size_bytes": self.size_bytes,
            "mtime": self.mtime,
            "perm_bits": self.perm_bits,
            "owner_uid": self.owner_uid,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DirEntry":
        return cls(
            name=data["name"],
            entry_type=data["entry_type"],
            target=data["target"],
            parent=data.get("parent", 0),
            size_bytes=data.get("size_bytes", 0),
            mtime=data.get("mtime", time.time()),
            perm_bits=data.get("perm_bits", 0o755),
            owner_uid=data.get("owner_uid", 0),
        )

class JournalStatus(Enum):
    PENDING = "PENDING"
    COMMITTED = "COMMITTED"
    ROLLED_BACK = "ROLLED_BACK"

@dataclass
class JournalRecord:
    txn_id: int
    op_type: str             # "WRITE" | "DELETE" | "MKDIR" | "DEFRAG"
    target: str
    old_state: Optional[Dict[str, Any]] = None
    new_state: Optional[Dict[str, Any]] = None
    status: JournalStatus = JournalStatus.PENDING
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "txn_id": self.txn_id,
            "op_type": self.op_type,
            "target": self.target,
            "old_state": self.old_state,
            "new_state": self.new_state,
            "status": self.status.value if isinstance(self.status, JournalStatus) else str(self.status),
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JournalRecord":
        return cls(
            txn_id=data["txn_id"],
            op_type=data["op_type"],
            target=data["target"],
            old_state=data.get("old_state"),
            new_state=data.get("new_state"),
            status=JournalStatus(data["status"]),
            timestamp=data.get("timestamp", time.time()),
        )

@dataclass
class VersionEntry:
    version_id: int
    file_path: str
    timestamp: float = field(default_factory=time.time)
    block_map: Optional[List[int]] = None
    diff: Optional[bytes] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version_id": self.version_id,
            "file_path": self.file_path,
            "timestamp": self.timestamp,
            "block_map": self.block_map,
            "diff": self.diff.hex() if self.diff else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VersionEntry":
        diff_bytes = bytes.fromhex(data["diff"]) if data.get("diff") else None
        return cls(
            version_id=data["version_id"],
            file_path=data["file_path"],
            timestamp=data.get("timestamp", time.time()),
            block_map=data.get("block_map"),
            diff=diff_bytes,
        )

@dataclass
class User:
    uid: int
    username: str
    password_hash: bytes
    salt: bytes
    role: str  # "admin" | "standard" | "guest"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uid": self.uid,
            "username": self.username,
            "password_hash": self.password_hash.hex(),
            "salt": self.salt.hex(),
            "role": self.role,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "User":
        return cls(
            uid=data["uid"],
            username=data["username"],
            password_hash=bytes.fromhex(data["password_hash"]),
            salt=bytes.fromhex(data["salt"]),
            role=data["role"],
        )

@dataclass
class Session:
    token: str
    uid: int
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 1800)

@dataclass
class QuotaRecord:
    uid: int
    limit_bytes: int
    used_bytes: int = 0

    def would_exceed(self, incoming_bytes: int) -> bool:
        return self.used_bytes + incoming_bytes > self.limit_bytes

@dataclass
class FileHandle:
    path: str
    target: int  # inode_id or cluster_id
    session: Session
    mode: str = "r"
