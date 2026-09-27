import os
import threading
from typing import Optional
from src.common.exceptions import CorruptDiskError, InvalidConfigError

class VirtualDisk:
    """Simulates physical disk I/O over a binary file (disk.img)."""
    def __init__(self):
        self._file_path: Optional[str] = None
        self._file_handle = None
        self._block_size: int = 4096
        self._disk_size: int = 0
        self._lock = threading.Lock()

    def open(self, path: str, create: bool = False, size_bytes: int = 0, block_size: int = 4096) -> None:
        with self._lock:
            self._file_path = path
            self._block_size = block_size
            if create:
                if size_bytes <= 0 or size_bytes % block_size != 0:
                    raise InvalidConfigError(f"Disk size {size_bytes} must be positive multiple of block size {block_size}")
                self._disk_size = size_bytes
                # Create and zero out the disk file
                with open(path, "wb") as f:
                    f.seek(size_bytes - 1)
                    f.write(b"\x00")
            
            if not os.path.exists(path):
                raise CorruptDiskError(f"Disk file does not exist: {path}")

            self._file_handle = open(path, "r+b")
            self._file_handle.seek(0, os.SEEK_END)
            self._disk_size = self._file_handle.tell()

    def close(self) -> None:
        with self._lock:
            if self._file_handle and not self._file_handle.closed:
                self._file_handle.flush()
                self._file_handle.close()
            self._file_handle = None

    @property
    def is_open(self) -> bool:
        return self._file_handle is not None and not self._file_handle.closed

    @property
    def block_size(self) -> int:
        return self._block_size

    @property
    def disk_size(self) -> int:
        return self._disk_size

    def read_block(self, block_id: int) -> bytes:
        with self._lock:
            if not self.is_open:
                raise CorruptDiskError("Disk is not open")
            offset = block_id * self._block_size
            if offset + self._block_size > self._disk_size:
                raise CorruptDiskError(f"Block ID {block_id} out of bounds")
            self._file_handle.seek(offset)
            data = self._file_handle.read(self._block_size)
            if len(data) < self._block_size:
                data = data.ljust(self._block_size, b"\x00")
            return data

    def write_block(self, block_id: int, data: bytes) -> None:
        with self._lock:
            if not self.is_open:
                raise CorruptDiskError("Disk is not open")
            offset = block_id * self._block_size
            if offset + self._block_size > self._disk_size:
                raise CorruptDiskError(f"Block ID {block_id} out of bounds")
            # Pad or truncate data to block_size
            padded = data[:self._block_size].ljust(self._block_size, b"\x00")
            self._file_handle.seek(offset)
            self._file_handle.write(padded)
            self._file_handle.flush()

    def read_raw(self, offset: int, length: int) -> bytes:
        with self._lock:
            if not self.is_open:
                raise CorruptDiskError("Disk is not open")
            self._file_handle.seek(offset)
            return self._file_handle.read(length)

    def write_raw(self, offset: int, data: bytes) -> None:
        with self._lock:
            if not self.is_open:
                raise CorruptDiskError("Disk is not open")
            self._file_handle.seek(offset)
            self._file_handle.write(data)
            self._file_handle.flush()

GLOBAL_DISK = VirtualDisk()
