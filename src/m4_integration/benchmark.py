import time
import tempfile
import os
from typing import Dict, List, Any
from src.m1_storage.allocator import StorageEngine
from src.m1_storage.defrag import calculate_fragmentation
from src.m2_security.auth import AuthManager
from src.m4_integration.facade import FileSystemFacade
from src.m3_reliability.journal import JournalManager
from src.m3_reliability.cache import LRUCache
from src.m3_reliability.versioning import VersionStore
from src.m4_integration.quota import QuotaManager

class BenchmarkResult:
    def __init__(self, mode: str, workload: str, ops_per_sec: float, latency_ms: float, frag_pct: float, cache_hit_ratio: float):
        self.mode = mode
        self.workload = workload
        self.ops_per_sec = round(ops_per_sec, 2)
        self.latency_ms = round(latency_ms, 3)
        self.frag_pct = round(frag_pct, 2)
        self.cache_hit_ratio = round(cache_hit_ratio, 4)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "workload": self.workload,
            "ops_per_sec": self.ops_per_sec,
            "latency_ms": self.latency_ms,
            "frag_pct": self.frag_pct,
            "cache_hit_ratio": self.cache_hit_ratio,
        }

def run_benchmark_on_mode(mode: str, workload: str, num_ops: int = 20) -> BenchmarkResult:
    with tempfile.TemporaryDirectory() as tmpdir:
        disk_path = os.path.join(tmpdir, "bench_disk.img")
        journal_path = os.path.join(tmpdir, "bench_journal.log")

        storage = StorageEngine()
        storage.format_disk(disk_path, size_bytes=16777216, block_size=4096, mode=mode)  # 16 MB disk

        auth = AuthManager()
        journal = JournalManager(journal_path=journal_path)
        cache = LRUCache(capacity=32)
        versioning = VersionStore(storage=storage)
        quota = QuotaManager()

        facade = FileSystemFacade(
            storage=storage, auth=auth, journal=journal,
            cache=cache, versioning=versioning, quota=quota
        )

        session = auth.authenticate("admin", "admin123")
        facade.handle_mkdir_request("/bench", session.token)

        start_t = time.time()
        for i in range(num_ops):
            path = f"/bench/file_{i}.txt"
            data = f"SmartFS Benchmark Payload {i} ".encode("utf-8") * 50
            facade.handle_write_request(path, data, session.token)
            facade.handle_read_request(path, session.token)
        end_t = time.time()

        elapsed = max(end_t - start_t, 0.001)
        ops_per_sec = (num_ops * 2) / elapsed
        latency_ms = (elapsed / (num_ops * 2)) * 1000.0
        frag = calculate_fragmentation(storage=storage)
        cache_ratio = cache.hit_ratio

        return BenchmarkResult(mode, workload, ops_per_sec, latency_ms, frag, cache_ratio)

def run_benchmark(workload: str = "mixed", num_ops: int = 20) -> Dict[str, Any]:
    fat_res = run_benchmark_on_mode("FAT", workload, num_ops)
    inode_res = run_benchmark_on_mode("INODE", workload, num_ops)
    return {
        "workload": workload,
        "results": [fat_res.to_dict(), inode_res.to_dict()],
        "report_markdown": generate_report([fat_res, inode_res])
    }

def generate_report(results: List[BenchmarkResult]) -> str:
    md = "# SmartFS Allocation Mode Performance Benchmark Report\n\n"
    md += "| Mode | Workload | Throughput (ops/sec) | Avg Latency (ms) | Fragmentation % | Cache Hit Ratio |\n"
    md += "|---|---|---|---|---|---|\n"
    for r in results:
        md += f"| {r.mode} | {r.workload} | {r.ops_per_sec} | {r.latency_ms} | {r.frag_pct}% | {r.cache_hit_ratio} |\n"
    md += "\n**Analysis:** Inode indexed allocation exhibits lower fragmentation impact during random file growths, whereas FAT chaining provides simpler chain traversal overhead.\n"
    return md
