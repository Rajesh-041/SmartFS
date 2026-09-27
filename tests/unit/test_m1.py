import tempfile
import os
import pytest
from src.m1_storage.allocator import StorageEngine
from src.common.exceptions import DiskFullError, ENOENT, EEXIST, ENOTEMPTY

def test_m1_disk_format_and_mount():
    with tempfile.TemporaryDirectory() as tmpdir:
        disk_path = os.path.join(tmpdir, "test_m1.img")
        storage = StorageEngine()
        sb = storage.format_disk(disk_path, size_bytes=16777216, block_size=4096, mode="FAT")
        assert sb.total_blocks == 4096
        assert sb.free_blocks == 4096 - 16

        storage.mount_disk(disk_path)
        assert storage.superblock.magic == b"SMFS"

def test_m1_allocation_and_chaining():
    with tempfile.TemporaryDirectory() as tmpdir:
        disk_path = os.path.join(tmpdir, "test_alloc.img")
        storage = StorageEngine()
        storage.format_disk(disk_path, size_bytes=1048576, block_size=4096, mode="FAT") # 256 blocks

        # Allocate chain
        start_cluster = storage.fat_alloc_chain(5)
        chain = storage.fat_chain(start_cluster)
        assert len(chain) == 5

        # Free chain
        freed = storage.fat_free_chain(start_cluster)
        assert len(freed) == 5
        assert len(storage.fat_chain(start_cluster)) == 0

def test_m1_inode_mode():
    with tempfile.TemporaryDirectory() as tmpdir:
        disk_path = os.path.join(tmpdir, "test_inode.img")
        storage = StorageEngine()
        storage.format_disk(disk_path, size_bytes=1048576, block_size=4096, mode="INODE")

        inode = storage.inode_allocate(owner_uid=1001, perm_bits=0o644)
        storage.inode_grow(inode, 3)
        assert len(inode.direct_blocks) == 3

        freed = storage.inode_free(inode.inode_id)
        assert len(freed) == 3

def test_m1_directory_operations():
    with tempfile.TemporaryDirectory() as tmpdir:
        disk_path = os.path.join(tmpdir, "test_dir.img")
        storage = StorageEngine()
        storage.format_disk(disk_path, size_bytes=1048576, block_size=4096, mode="FAT")

        storage.mkdir("/home")
        storage.mkdir("/home/alice")
        entries = storage.list_dir("/home")
        assert len(entries) == 1
        assert entries[0].name == "alice"

        with pytest.raises(ENOTEMPTY):
            storage.rmdir("/home")

        storage.rmdir("/home/alice")
        assert len(storage.list_dir("/home")) == 0

def test_m1_disk_full_error():
    with tempfile.TemporaryDirectory() as tmpdir:
        disk_path = os.path.join(tmpdir, "test_full.img")
        storage = StorageEngine()
        storage.format_disk(disk_path, size_bytes=131072, block_size=4096, mode="FAT") # 32 blocks (16 metadata, 16 free)

        with pytest.raises(DiskFullError):
            storage.allocate_blocks(20)
