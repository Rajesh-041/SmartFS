import json
import os
import time
import threading
from typing import List, Optional, Dict, Union, Tuple, Any

from src.common.exceptions import (
    InvalidConfigError, CorruptDiskError, DiskFullError,
    ENOENT, EEXIST, ENOTEMPTY
)
from src.common.models import (
    Superblock, FreeBitmap, FatTable, Inode, InodeTable,
    DirEntry, FileHandle, FAT_EOF, FAT_FREE, MAGIC_BYTES
)
from src.common.event_bus import emit_metric
from src.m1_storage.disk import GLOBAL_DISK, VirtualDisk

RESERVED_METADATA_BLOCKS = 16

class StorageEngine:
    """M1 Storage Engine managing allocation, directories, FAT/Inode tables, disk metadata."""
    def __init__(self, disk: VirtualDisk = GLOBAL_DISK):
        self.disk = disk
        self.superblock: Optional[Superblock] = None
        self.bitmap: Optional[FreeBitmap] = None
        self.fat_table: Optional[FatTable] = None
        self.inode_table: Optional[InodeTable] = None
        self.directories: Dict[str, DirEntry] = {}  # path -> DirEntry
        self._lock = threading.Lock()

    def format_disk(self, path: str, size_bytes: int = 67108864, block_size: int = 4096, mode: str = "FAT") -> Superblock:
        if size_bytes <= 0 or size_bytes % block_size != 0:
            raise InvalidConfigError(f"size_bytes ({size_bytes}) must be positive multiple of block_size ({block_size})")

        mode_upper = mode.upper()
        if mode_upper not in ("FAT", "INODE"):
            raise InvalidConfigError(f"Invalid allocation mode: {mode}")

        total_blocks = size_bytes // block_size
        sb = Superblock(
            magic=MAGIC_BYTES,
            disk_size=size_bytes,
            block_size=block_size,
            total_blocks=total_blocks,
            free_blocks=total_blocks - RESERVED_METADATA_BLOCKS,
            allocation_mode=mode_upper,
            root_dir_ptr=0,
            fs_version=1
        )

        bitmap = FreeBitmap(total_blocks)
        # Mark reserved blocks
        for i in range(RESERVED_METADATA_BLOCKS):
            bitmap.mark(i, allocated=True)

        fat = FatTable(total_blocks)
        for i in range(RESERVED_METADATA_BLOCKS):
            fat.entries[i] = FAT_EOF

        inodes = InodeTable()
        root_inode = inodes.allocate_inode(owner_uid=0, group_gid=0, perm_bits=0o755)

        # Create root directory entry
        directories = {
            "/": DirEntry(name="/", entry_type="dir", target=root_inode.inode_id if mode_upper == "INODE" else 0, parent=0, perm_bits=0o755)
        }

        self.disk.open(path, create=True, size_bytes=size_bytes, block_size=block_size)

        with self._lock:
            self.superblock = sb
            self.bitmap = bitmap
            self.fat_table = fat
            self.inode_table = inodes
            self.directories = directories
            self._save_metadata()

        return sb

    def mount_disk(self, path: str) -> Superblock:
        if not os.path.exists(path):
            raise CorruptDiskError(f"Disk image file not found: {path}")

        self.disk.open(path, create=False)
        with self._lock:
            self._load_metadata()
            if self.superblock is None or self.superblock.magic != MAGIC_BYTES:
                raise CorruptDiskError("Invalid superblock or bad magic bytes")
        return self.superblock

    def _save_metadata(self) -> None:
        """Persists all metadata (superblock, bitmap, FAT/inodes, directories) to reserved blocks."""
        if not self.superblock:
            return

        # Block 0: Superblock
        sb_bytes = json.dumps(self.superblock.to_dict()).encode("utf-8")
        self.disk.write_block(0, sb_bytes)

        # Block 1: FreeBitmap
        bm_bytes = bytes(self.bitmap.bits)
        self.disk.write_block(1, bm_bytes)

        # Block 2: FAT / Inodes
        fat_data = json.dumps(self.fat_table.entries).encode("utf-8")
        self.disk.write_block(2, fat_data)

        inode_data = json.dumps({k: v.to_dict() for k, v in self.inode_table.inodes.items()}).encode("utf-8")
        self.disk.write_block(3, inode_data)

        # Block 4: Directory Map
        dir_data = json.dumps({k: v.to_dict() for k, v in self.directories.items()}).encode("utf-8")
        self.disk.write_block(4, dir_data)

    def _load_metadata(self) -> None:
        """Loads metadata from reserved blocks."""
        try:
            # Block 0
            sb_raw = self.disk.read_block(0).decode("utf-8").rstrip("\x00")
            sb_dict = json.loads(sb_raw)
            self.superblock = Superblock.from_dict(sb_dict)
            if self.superblock.magic != MAGIC_BYTES:
                raise CorruptDiskError("Bad magic bytes in superblock")

            # Block 1
            bm_raw = self.disk.read_block(1)
            self.bitmap = FreeBitmap(self.superblock.total_blocks, bytearray(bm_raw[:(self.superblock.total_blocks + 7) // 8]))

            # Block 2
            fat_raw = self.disk.read_block(2).decode("utf-8").rstrip("\x00")
            fat_entries = json.loads(fat_raw) if fat_raw else [FAT_FREE] * self.superblock.total_blocks
            self.fat_table = FatTable(self.superblock.total_blocks, fat_entries)

            # Block 3
            inode_raw = self.disk.read_block(3).decode("utf-8").rstrip("\x00")
            inode_dict = json.loads(inode_raw) if inode_raw else {}
            parsed_inodes = {int(k): Inode.from_dict(v) for k, v in inode_dict.items()}
            self.inode_table = InodeTable(parsed_inodes)

            # Block 4
            dir_raw = self.disk.read_block(4).decode("utf-8").rstrip("\x00")
            dir_dict = json.loads(dir_raw) if dir_raw else {}
            self.directories = {k: DirEntry.from_dict(v) for k, v in dir_dict.items()}

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise CorruptDiskError(f"Corrupt metadata on disk: {e}")

    # --- Allocation API ---

    def allocate_block(self) -> int:
        with self._lock:
            block_id = self.bitmap.find_first_free()
            if block_id is None:
                raise DiskFullError("No free blocks remaining on virtual disk")
            self.bitmap.mark(block_id, allocated=True)
            self.superblock.free_blocks = self.bitmap.count_free()
            self._save_metadata()

        emit_metric("disk_usage_changed", {
            "used_blocks": self.superblock.total_blocks - self.superblock.free_blocks,
            "total_blocks": self.superblock.total_blocks,
            "free_blocks": self.superblock.free_blocks
        })
        return block_id

    def allocate_blocks(self, n: int, strategy: str = "linked") -> List[int]:
        with self._lock:
            if n <= 0:
                return []
            if self.bitmap.count_free() < n:
                raise DiskFullError(f"Requested {n} blocks, but only {self.bitmap.count_free()} free")

            if strategy == "contiguous":
                allocated = self.bitmap.find_free_run(n)
                if not allocated or len(allocated) < n:
                    raise DiskFullError(f"Cannot find contiguous run of {n} blocks")
            else:  # "linked" or "indexed"
                allocated = []
                for _ in range(n):
                    b = self.bitmap.find_first_free()
                    if b is None:
                        raise DiskFullError("Disk full during multi-block allocation")
                    self.bitmap.mark(b, allocated=True)
                    allocated.append(b)

            if strategy == "contiguous":
                for b in allocated:
                    self.bitmap.mark(b, allocated=True)

            self.superblock.free_blocks = self.bitmap.count_free()
            self._save_metadata()

        emit_metric("disk_usage_changed", {
            "used_blocks": self.superblock.total_blocks - self.superblock.free_blocks,
            "total_blocks": self.superblock.total_blocks,
            "free_blocks": self.superblock.free_blocks
        })
        return allocated

    def free_block(self, block_id: int) -> None:
        with self._lock:
            if block_id < RESERVED_METADATA_BLOCKS:
                return  # Never free reserved metadata blocks
            self.bitmap.mark(block_id, allocated=False)
            if self.superblock:
                self.superblock.free_blocks = self.bitmap.count_free()
            self._save_metadata()

        if self.superblock:
            emit_metric("disk_usage_changed", {
                "used_blocks": self.superblock.total_blocks - self.superblock.free_blocks,
                "total_blocks": self.superblock.total_blocks,
                "free_blocks": self.superblock.free_blocks
            })

    def find_free_blocks(self, n: int) -> List[int]:
        with self._lock:
            result = []
            for i in range(self.superblock.total_blocks):
                if self.bitmap.is_free(i):
                    result.append(i)
                    if len(result) == n:
                        break
            return result

    # --- FAT Mode ---

    def fat_alloc_chain(self, n_blocks: int) -> int:
        if n_blocks <= 0:
            return FAT_EOF
        chain = self.allocate_blocks(n_blocks, strategy="linked")
        with self._lock:
            for i in range(len(chain) - 1):
                self.fat_table.link(chain[i], chain[i + 1])
            self.fat_table.link(chain[-1], FAT_EOF)
            self._save_metadata()
        return chain[0]

    def fat_free_chain(self, start: int) -> List[int]:
        with self._lock:
            freed = self.fat_table.free_chain(start)
            for b in freed:
                if b >= RESERVED_METADATA_BLOCKS:
                    self.bitmap.mark(b, allocated=False)
            if self.superblock:
                self.superblock.free_blocks = self.bitmap.count_free()
            self._save_metadata()
        return freed

    def fat_chain(self, start: int) -> List[int]:
        with self._lock:
            return self.fat_table.chain(start)

    # --- Inode Mode ---

    def inode_allocate(self, owner_uid: int = 0, group_gid: int = 0, perm_bits: int = 0o644) -> Inode:
        with self._lock:
            inode = self.inode_table.allocate_inode(owner_uid=owner_uid, group_gid=group_gid, perm_bits=perm_bits)
            self._save_metadata()
            return inode

    def inode_grow(self, inode: Inode, n_blocks: int) -> None:
        new_blocks = self.allocate_blocks(n_blocks, strategy="indexed")
        with self._lock:
            for b in new_blocks:
                if len(inode.direct_blocks) < DIRECT_LIMIT:
                    inode.direct_blocks.append(b)
                else:
                    if inode.indirect_block is None:
                        indirect_b = self.bitmap.find_first_free()
                        if indirect_b is None:
                            raise DiskFullError("Disk full allocating indirect block")
                        self.bitmap.mark(indirect_b, allocated=True)
                        inode.indirect_block = indirect_b
            self._save_metadata()

    def inode_free(self, inode_id: int) -> List[int]:
        with self._lock:
            freed_blocks = self.inode_table.free_inode(inode_id)
            for b in freed_blocks:
                if b >= RESERVED_METADATA_BLOCKS:
                    self.bitmap.mark(b, allocated=False)
            if self.superblock:
                self.superblock.free_blocks = self.bitmap.count_free()
            self._save_metadata()
            return freed_blocks

    # --- Directory & Path Resolution ---

    def _normalize_path(self, path: str) -> str:
        path = path.strip()
        if not path.startswith("/"):
            path = "/" + path
        parts = [p for p in path.split("/") if p and p != "."]
        res = []
        for p in parts:
            if p == "..":
                if res:
                    res.pop()
            else:
                res.append(p)
        return "/" + "/".join(res)

    def resolve_path(self, path: str) -> Optional[DirEntry]:
        norm = self._normalize_path(path)
        with self._lock:
            return self.directories.get(norm)

    def mkdir(self, path: str, owner_uid: int = 0, perm_bits: int = 0o755) -> DirEntry:
        norm = self._normalize_path(path)
        if norm == "/":
            return self.directories["/"]

        with self._lock:
            if norm in self.directories:
                raise EEXIST(f"Directory already exists: {norm}")

            parent_path = self._normalize_path(os.path.dirname(norm))
            if parent_path not in self.directories or self.directories[parent_path].entry_type != "dir":
                raise ENOENT(f"Parent directory not found: {parent_path}")

            target_id = 0
            if self.superblock.allocation_mode == "INODE":
                inode = self.inode_table.allocate_inode(owner_uid=owner_uid, perm_bits=perm_bits)
                target_id = inode.inode_id

            entry = DirEntry(
                name=os.path.basename(norm),
                entry_type="dir",
                target=target_id,
                parent=self.directories[parent_path].target,
                perm_bits=perm_bits,
                owner_uid=owner_uid
            )
            self.directories[norm] = entry
            self._save_metadata()
            return entry

    def rmdir(self, path: str) -> None:
        norm = self._normalize_path(path)
        if norm == "/":
            raise PermissionDenied("Cannot delete root directory")

        with self._lock:
            if norm not in self.directories:
                raise ENOENT(f"Directory not found: {norm}")

            entry = self.directories[norm]
            if entry.entry_type != "dir":
                raise ENOENT(f"Path is not a directory: {norm}")

            # Check if directory is empty
            prefix = norm if norm.endswith("/") else norm + "/"
            has_children = any(k.startswith(prefix) for k in self.directories.keys() if k != norm)
            if has_children:
                raise ENOTEMPTY(f"Directory not empty: {norm}")

            if self.superblock.allocation_mode == "INODE" and entry.target in self.inode_table.inodes:
                self.inode_table.free_inode(entry.target)

            del self.directories[norm]
            self._save_metadata()

    def list_dir(self, path: str) -> List[DirEntry]:
        norm = self._normalize_path(path)
        with self._lock:
            if norm not in self.directories:
                raise ENOENT(f"Directory not found: {norm}")

            prefix = norm if norm.endswith("/") else norm + "/"
            children = []
            for k, v in self.directories.items():
                if k == norm:
                    continue
                if k.startswith(prefix):
                    rel = k[len(prefix):]
                    if "/" not in rel:
                        children.append(v)
            return children

    # --- File Operations ---

    def create_file(self, path: str, owner_uid: int = 0, perm_bits: int = 0o644) -> DirEntry:
        norm = self._normalize_path(path)
        with self._lock:
            if norm in self.directories:
                raise EEXIST(f"File already exists: {norm}")

            parent_path = self._normalize_path(os.path.dirname(norm))
            if parent_path not in self.directories or self.directories[parent_path].entry_type != "dir":
                raise ENOENT(f"Parent directory not found: {parent_path}")

            target_id = FAT_EOF
            if self.superblock.allocation_mode == "INODE":
                inode = self.inode_table.allocate_inode(owner_uid=owner_uid, perm_bits=perm_bits)
                target_id = inode.inode_id

            entry = DirEntry(
                name=os.path.basename(norm),
                entry_type="file",
                target=target_id,
                parent=self.directories[parent_path].target,
                size_bytes=0,
                mtime=time.time(),
                perm_bits=perm_bits,
                owner_uid=owner_uid
            )
            self.directories[norm] = entry
            self._save_metadata()
            return entry

    def get_file_blocks(self, path: str) -> List[int]:
        norm = self._normalize_path(path)
        with self._lock:
            if norm not in self.directories:
                raise ENOENT(f"File not found: {norm}")
            entry = self.directories[norm]
            if self.superblock.allocation_mode == "FAT":
                if entry.target == FAT_EOF or entry.target == FAT_FREE:
                    return []
                return self.fat_table.chain(entry.target)
            else:
                inode = self.inode_table.inodes.get(entry.target)
                return list(inode.direct_blocks) if inode else []

    def write_file_blocks(self, path: str, payload_blocks: List[bytes]) -> int:
        """Low-level write of encrypted/compressed payload blocks to physical disk."""
        norm = self._normalize_path(path)
        n = len(payload_blocks)
        if n == 0:
            return 0

        allocated_ids = self.allocate_blocks(n)
        with self._lock:
            entry = self.directories.get(norm)
            if not entry:
                raise ENOENT(f"File not found: {norm}")

            # Write physical blocks
            total_bytes = sum(len(b) for b in payload_blocks)
            for idx, block_data in enumerate(payload_blocks):
                block_id = allocated_ids[idx]
                self.disk.write_block(block_id, block_data)

            if self.superblock.allocation_mode == "FAT":
                # Free old chain if exists
                if entry.target != FAT_EOF and entry.target != FAT_FREE:
                    self.fat_table.free_chain(entry.target)
                # Link new chain
                for i in range(len(allocated_ids) - 1):
                    self.fat_table.link(allocated_ids[i], allocated_ids[i + 1])
                self.fat_table.link(allocated_ids[-1], FAT_EOF)
                entry.target = allocated_ids[0]
            else:
                inode = self.inode_table.inodes.get(entry.target)
                if inode:
                    for b in inode.direct_blocks:
                        self.bitmap.mark(b, allocated=False)
                    inode.direct_blocks = allocated_ids
                    inode.size_bytes = total_bytes
                    inode.mtime = time.time()

            entry.size_bytes = total_bytes
            entry.mtime = time.time()
            self._save_metadata()
            return total_bytes

    def read_file_blocks(self, path: str) -> List[bytes]:
        block_ids = self.get_file_blocks(path)
        blocks = []
        for bid in block_ids:
            blocks.append(self.disk.read_block(bid))
        return blocks

    def delete_file(self, path: str) -> None:
        norm = self._normalize_path(path)
        with self._lock:
            if norm not in self.directories:
                raise ENOENT(f"File not found: {norm}")
            entry = self.directories[norm]
            if entry.entry_type != "file":
                raise ENOENT(f"Path is not a file: {norm}")

            if self.superblock.allocation_mode == "FAT":
                if entry.target != FAT_EOF and entry.target != FAT_FREE:
                    freed = self.fat_table.free_chain(entry.target)
                    for b in freed:
                        self.bitmap.mark(b, allocated=False)
            else:
                if entry.target in self.inode_table.inodes:
                    freed = self.inode_table.free_inode(entry.target)
                    for b in freed:
                        self.bitmap.mark(b, allocated=False)

            del self.directories[norm]
            if self.superblock:
                self.superblock.free_blocks = self.bitmap.count_free()
            self._save_metadata()

        if self.superblock:
            emit_metric("disk_usage_changed", {
                "used_blocks": self.superblock.total_blocks - self.superblock.free_blocks,
                "total_blocks": self.superblock.total_blocks,
                "free_blocks": self.superblock.free_blocks
            })

GLOBAL_STORAGE = StorageEngine()
