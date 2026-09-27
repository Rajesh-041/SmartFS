from typing import Optional, List
from src.m1_storage.allocator import GLOBAL_STORAGE, StorageEngine
from src.common.event_bus import emit_metric
from src.common.exceptions import ENOENT

def calculate_fragmentation(path: Optional[str] = None, storage: StorageEngine = GLOBAL_STORAGE) -> float:
    """Calculates fragmentation percentage for a specific file or across the entire disk."""
    if path:
        entry = storage.resolve_path(path)
        if not entry or entry.entry_type != "file":
            raise ENOENT(f"File not found for defrag analysis: {path}")
        chain = storage.get_file_blocks(path)
        if len(chain) <= 1:
            frag = 0.0
        else:
            non_contiguous = sum(1 for i in range(len(chain) - 1) if chain[i + 1] != chain[i] + 1)
            frag = (non_contiguous / (len(chain) - 1)) * 100.0
    else:
        file_paths = [p for p, e in storage.directories.items() if e.entry_type == "file"]
        if not file_paths:
            frag = 0.0
        else:
            total_frags = 0.0
            count = 0
            for p in file_paths:
                chain = storage.get_file_blocks(p)
                if len(chain) > 1:
                    non_contig = sum(1 for i in range(len(chain) - 1) if chain[i + 1] != chain[i] + 1)
                    total_frags += (non_contig / (len(chain) - 1)) * 100.0
                    count += 1
            frag = total_frags / count if count > 0 else 0.0

    frag_val = round(frag, 2)
    emit_metric("fragmentation_reported", {"path": path or "disk_wide", "fragmentation_pct": frag_val})
    return frag_val

def defragment(path: str, storage: StorageEngine = GLOBAL_STORAGE) -> None:
    """Defragments a file by rewriting its blocks contiguously."""
    entry = storage.resolve_path(path)
    if not entry or entry.entry_type != "file":
        raise ENOENT(f"File not found for defragmentation: {path}")

    old_chain = storage.get_file_blocks(path)
    if len(old_chain) <= 1:
        return

    # Read current blocks
    blocks = storage.read_file_blocks(path)

    # Re-allocate contiguously
    storage.write_file_blocks(path, blocks)
    
    # Calculate new fragmentation
    new_frag = calculate_fragmentation(path, storage)
    emit_metric("defrag_completed", {"path": path, "new_fragmentation_pct": new_frag})
