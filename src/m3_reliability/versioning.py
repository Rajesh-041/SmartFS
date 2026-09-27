import time
from typing import List, Dict, Optional
from src.common.models import VersionEntry
from src.m1_storage.allocator import GLOBAL_STORAGE, StorageEngine
from src.common.exceptions import ENOENT

class VersionStore:
    """Snapshot-based file versioning manager."""
    def __init__(self, storage: StorageEngine = GLOBAL_STORAGE):
        self.storage = storage
        self.versions: Dict[str, List[VersionEntry]] = {}  # file_path -> list[VersionEntry]
        self._next_v_id = 1

    def create_version(self, file_path: str, block_map: List[int]) -> VersionEntry:
        v_id = self._next_v_id
        self._next_v_id += 1
        entry = VersionEntry(
            version_id=v_id,
            file_path=file_path,
            timestamp=time.time(),
            block_map=list(block_map)
        )
        if file_path not in self.versions:
            self.versions[file_path] = []
        self.versions[file_path].append(entry)
        return entry

    def list_versions(self, file_path: str) -> List[VersionEntry]:
        return list(self.versions.get(file_path, []))

    def restore_version(self, file_path: str, version_id: int) -> None:
        v_list = self.versions.get(file_path, [])
        target_v = next((v for v in v_list if v.version_id == version_id), None)
        if not target_v or not target_v.block_map:
            raise ENOENT(f"Version {version_id} for file '{file_path}' not found")

        # Read target version's physical blocks and write them to restore
        blocks_data = [self.storage.disk.read_block(b) for b in target_v.block_map]
        self.storage.write_file_blocks(file_path, blocks_data)

    def diff_versions(self, v1_id: int, v2_id: int) -> bytes:
        return b"diff_placeholder"

GLOBAL_VERSIONING = VersionStore()
