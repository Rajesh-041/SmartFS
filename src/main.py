import sys
import os
import shlex
import argparse
from typing import Optional

from src.m4_integration.facade import GLOBAL_FACADE, FileSystemFacade
from src.m2_security.auth import GLOBAL_AUTH
from src.m1_storage.defrag import calculate_fragmentation, defragment
from src.m3_reliability.versioning import GLOBAL_VERSIONING
from src.m4_integration.benchmark import run_benchmark
from src.common.exceptions import SmartFSError, SimulatedCrashError

def print_banner():
    print("=" * 65)
    print("      SmartFS — Secure & Intelligent File System Simulator")
    print("=================================================================")
    print(" Type 'help' for available commands. Try 'login admin admin123'")
    print("=" * 65)

class SmartFSCLI:
    def __init__(self, facade: FileSystemFacade = GLOBAL_FACADE):
        self.facade = facade
        self.current_token: Optional[str] = None
        self.current_user: Optional[str] = None
        self.current_role: Optional[str] = None

    def start(self):
        # Initial boot & recovery
        print("[BOOT] Mounting disk and running crash recovery scan...")
        rec = self.facade.handle_boot("disk.img")
        print(f"[RECOVERY] Journal scan complete. Pending entries rolled back: {rec['rolled_back']}, Committed: {rec['committed_count']}, Orphaned blocks reclaimed: {rec['orphaned_reclaimed']}")
        print("[OK] System clean and ready.\n")

        print_banner()

        while True:
            try:
                prompt = f"SmartFS ({self.current_user or 'guest'})> "
                raw_input = input(prompt).strip()
                if not raw_input:
                    continue
                if raw_input.lower() in ("exit", "quit"):
                    print("Exiting SmartFS simulator. Goodbye!")
                    break
                self.execute_command(raw_input)
            except KeyboardInterrupt:
                print("\nUse 'exit' to quit.")
            except EOFError:
                break

    def execute_command(self, cmd_line: str):
        try:
            tokens = shlex.split(cmd_line)
        except Exception as e:
            print(f"[ERROR] Command parsing failed: {e}")
            return

        cmd = tokens[0].lower()
        args = tokens[1:]

        try:
            if cmd == "help":
                self.cmd_help()
            elif cmd == "login":
                self.cmd_login(args)
            elif cmd == "logout":
                self.cmd_logout()
            elif cmd == "mkdir":
                self.cmd_mkdir(args)
            elif cmd == "rmdir":
                self.cmd_rmdir(args)
            elif cmd in ("ls", "dir"):
                self.cmd_ls(args)
            elif cmd == "write":
                self.cmd_write(args)
            elif cmd == "read":
                self.cmd_read(args)
            elif cmd == "delete":
                self.cmd_delete(args)
            elif cmd == "versions":
                self.cmd_versions(args)
            elif cmd == "restore":
                self.cmd_restore(args)
            elif cmd == "defrag":
                self.cmd_defrag(args)
            elif cmd == "benchmark":
                self.cmd_benchmark(args)
            elif cmd == "simulate-crash":
                self.cmd_simulate_crash(args)
            elif cmd in ("restart", "boot"):
                self.cmd_restart()
            elif cmd == "status":
                self.cmd_status()
            elif cmd == "format":
                self.cmd_format(args)
            else:
                print(f"[ERROR] Unknown command '{cmd}'. Type 'help' for available commands.")
        except SmartFSError as e:
            print(f"[ERROR] {e.__class__.__name__}: {e}")
        except Exception as e:
            print(f"[UNEXPECTED ERROR] {e}")

    def cmd_help(self):
        print("""
Available Commands:
  login <username> <password>           Log in (default: admin/admin123, alice/alice123)
  logout                                End current session
  format [--size 64M] [--mode fat|inode] Format virtual disk image
  mkdir <path>                          Create directory
  rmdir <path>                          Remove empty directory
  ls [path]                             List directory contents
  write <path> "<data>"                 Write file (encrypts, compresses, journals)
  read <path>                           Read and decrypt file
  delete <path>                         Delete file
  versions <path>                       List version snapshots for file
  restore <path> <version_id>           Restore file to historical version snapshot
  defrag [path]                         Calculate or run defragmentation
  benchmark                             Run FAT vs INODE performance benchmark comparison
  simulate-crash --during <stage>       Test crash recovery (stages: journal, allocate, physical_write, commit)
  restart / boot                        Mount disk and run WAL crash recovery replay
  status                                Display system, session, and metrics status
  exit                                  Quit simulator
""")

    def cmd_login(self, args):
        if len(args) < 2:
            print("Usage: login <username> <password>")
            return
        username, password = args[0], args[1]
        session = GLOBAL_AUTH.authenticate(username, password)
        user = GLOBAL_AUTH.get_user_by_id(session.uid)
        self.current_token = session.token
        self.current_user = username
        self.current_role = user.role if user else "standard"
        print(f"[OK] Logged in as '{username}' (role={self.current_role}, token={session.token[:8]}...)")

    def cmd_logout(self):
        if self.current_token:
            GLOBAL_AUTH.revoke_session(self.current_token)
        self.current_token = None
        self.current_user = None
        self.current_role = None
        print("[OK] Logged out.")

    def _require_auth(self):
        if not self.current_token:
            raise SmartFSError("Authentication required. Please 'login' first.")
        return self.current_token

    def cmd_mkdir(self, args):
        token = self._require_auth()
        if not args:
            print("Usage: mkdir <path>")
            return
        path = args[0]
        self.facade.handle_mkdir_request(path, token)
        print(f"[OK] Directory created: {path}")

    def cmd_rmdir(self, args):
        token = self._require_auth()
        if not args:
            print("Usage: rmdir <path>")
            return
        path = args[0]
        self.facade.storage.rmdir(path)
        print(f"[OK] Directory removed: {path}")

    def cmd_ls(self, args):
        token = self._require_auth()
        path = args[0] if args else "/"
        entries = self.facade.handle_list_request(path, token)
        if not entries:
            print(f"(directory '{path}' is empty)")
            return
        print(f"Contents of {path}:")
        print(f"{'TYPE':<6} {'NAME':<20} {'SIZE':<10} {'PERM':<6}")
        print("-" * 46)
        for e in entries:
            t = "<DIR>" if e.entry_type == "dir" else "FILE"
            print(f"{t:<6} {e.name:<20} {e.size_bytes:<10} {oct(e.perm_bits):<6}")

    def cmd_write(self, args):
        token = self._require_auth()
        if len(args) < 2:
            print("Usage: write <path> \"<content>\"")
            return
        path = args[0]
        content = " ".join(args[1:]).encode("utf-8")
        written = self.facade.handle_write_request(path, content, token)
        user = GLOBAL_AUTH.get_user_by_id(GLOBAL_AUTH.validate_session(token).uid)
        quota = self.facade.quota.get_quota(user.uid)
        print(f"[JOURNAL] WRITE PENDING -> COMMITTED")
        print(f"[OK] {written} bytes written to '{path}'. Quota usage: {quota.used_bytes}/{quota.limit_bytes} bytes.")

    def cmd_read(self, args):
        token = self._require_auth()
        if not args:
            print("Usage: read <path>")
            return
        path = args[0]
        content = self.facade.handle_read_request(path, token)
        print(content.decode("utf-8", errors="replace"))

    def cmd_delete(self, args):
        token = self._require_auth()
        if not args:
            print("Usage: delete <path>")
            return
        path = args[0]
        self.facade.handle_delete_request(path, token)
        print(f"[OK] File '{path}' deleted.")

    def cmd_versions(self, args):
        if not args:
            print("Usage: versions <path>")
            return
        path = args[0]
        versions = GLOBAL_VERSIONING.list_versions(path)
        if not versions:
            print(f"No version history for '{path}'")
            return
        print(f"Version History for {path}:")
        for v in versions:
            print(f"  v{v.version_id} | timestamp: {v.timestamp:.2f} | blocks: {v.block_map}")

    def cmd_restore(self, args):
        if len(args) < 2:
            print("Usage: restore <path> <version_id>")
            return
        path, v_id = args[0], int(args[1])
        GLOBAL_VERSIONING.restore_version(path, v_id)
        print(f"[OK] File '{path}' restored to version snapshot #{v_id}.")

    def cmd_defrag(self, args):
        path = args[0] if args else None
        if path:
            frag_before = calculate_fragmentation(path, self.facade.storage)
            print(f"Defragmenting '{path}' (fragmentation before: {frag_before}%)...")
            defragment(path, self.facade.storage)
            frag_after = calculate_fragmentation(path, self.facade.storage)
            print(f"[OK] Defragmentation complete. Fragmentation after: {frag_after}%.")
        else:
            frag = calculate_fragmentation(None, self.facade.storage)
            print(f"Disk-wide fragmentation: {frag}%")

    def cmd_benchmark(self, args):
        print("Running FAT vs INODE synthetic benchmark suite...")
        res = run_benchmark("mixed", num_ops=25)
        print("\n" + res["report_markdown"])

    def cmd_simulate_crash(self, args):
        token = self._require_auth()
        stage = "journal"
        if "--during" in args:
            idx = args.index("--during")
            if idx + 1 < len(args):
                stage = args[idx + 1]
        
        print(f"[SIMULATION] Injecting crash during stage '{stage}'...")
        try:
            self.facade.handle_write_request("/crash_test.txt", b"crash data payload", token, _fail_after=stage)
        except SimulatedCrashError as e:
            print(f"[SIMULATED CRASH SUCCESSFUL] {e}")
            print("Run 'restart' or 'boot' to trigger WAL crash recovery replay.")

    def cmd_restart(self):
        print("[RECOVERY] Scanning WAL journal log...")
        report = self.facade.handle_boot("disk.img")
        print(f"[RECOVERY] Pending entries found & rolled back: {report['rolled_back']}")
        print(f"[RECOVERY] Bitmap & allocation tables re-validated, {report['orphaned_reclaimed']} orphaned blocks reclaimed.")
        print("[OK] System clean, resuming normal operations.")

    def cmd_status(self):
        sb = self.facade.storage.superblock
        mode = sb.allocation_mode if sb else "UNKNOWN"
        used = sb.total_blocks - sb.free_blocks if sb else 0
        total = sb.total_blocks if sb else 0
        cache_ratio = self.facade.cache.hit_ratio
        frag = calculate_fragmentation(None, self.facade.storage)
        print(f"System Status:")
        print(f"  Disk Mode: {mode}")
        print(f"  Used Blocks: {used} / {total} ({(used/total)*100:.1f}%)")
        print(f"  Cache Hit Ratio: {cache_ratio * 100:.1f}%")
        print(f"  Fragmentation: {frag}%")
        print(f"  Current Session: {self.current_user or 'None'} ({self.current_role or 'N/A'})")

    def cmd_format(self, args):
        parser = argparse.ArgumentParser(prog="format")
        parser.add_argument("--size", default="64M")
        parser.add_argument("--mode", default="fat", choices=["fat", "inode"])
        parsed, _ = parser.parse_known_args(args)
        size_str = parsed.size.upper()
        if size_str.endswith("M"):
            size_b = int(size_str[:-1]) * 1024 * 1024
        else:
            size_b = int(size_str)
        sb = self.facade.storage.format_disk("disk.img", size_bytes=size_b, mode=parsed.mode.upper())
        print(f"[OK] Disk formatted ({parsed.size}, mode={sb.allocation_mode}).")

def main():
    cli = SmartFSCLI()
    cli.start()

if __name__ == "__main__":
    main()
