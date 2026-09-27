# SmartFS — A Secure and Intelligent File System Simulator

SmartFS is a simulated file system built to demonstrate, in working code, the core subsystems of a real OS storage stack: allocation and directory management, access control and encryption, write-ahead logging and crash recovery, caching and versioning, and a live analytics/quota layer that ties everything together.

It features both a **C (C99)** implementation and a **Python** reference implementation, complete with native support for running as a user program inside **xv6 OS (RISC-V/x86)** under QEMU on Ubuntu.

---

## 1. What SmartFS Does

- **Multi-user authentication** with hashed passwords (PBKDF2/bcrypt), cryptographically random session tokens, and role-based access control (Admin / Standard / Guest).
- **Unix-style 9-bit permission bits** (owner/group/others `rwx`) enforced per file.
- **Two selectable allocation strategies** — FAT-style chaining and Inode-style indexed allocation — switchable at format time for performance comparison.
- **Nested directories** with full path resolution (`/home/user/file.txt`).
- **Write-ahead logging (WAL)** so every mutating operation is crash-safe with synchronous disk flushes.
- **Crash recovery engine** that unwinds incomplete (`PENDING`) transactions via undo-logging and reclaims orphaned blocks on restart.
- **Snapshot file versioning** — snapshot-based rollback to any prior file state.
- **Transparent compression and encryption** — payload compression (zlib / RLE) followed by AES-256 GCM encryption on write (and inverse decryption followed by decompression on read).
- **O(1) LRU block cache** with doubly-linked list & hash map tracking real-time hit/miss ratios.
- **Per-user storage quotas** enforced before block allocation or journaling.
- **On-demand and background defragmentation** with before/after fragmentation metrics.
- **Real-time analytics dashboard**: live disk usage, fragmentation, cache hit ratio, per-user quotas, security audit access logs, and WAL recovery events.

---

## 2. System Architecture & Layered Request Pipeline

Requests flow top-down; data, status, and errors flow bottom-up. The Analytics layer is **non-blocking** — it listens to events emitted by every layer rather than being polled synchronously.

```
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 1 — USER INTERFACE                                         │
│   CLI / GUI: login, file browser, admin panel                    │
└──────────────────────────────┬────────────────────────────────────┘
                                │ user command (verb + args + session)
┌──────────────────────────────▼────────────────────────────────────┐
│ LAYER 2 — SECURITY & ACCESS CONTROL                               │
│   Authentication → Session/Token → RBAC Check → Permission Bits   │
└──────────────────────────────┬────────────────────────────────────┘
                                │ authorized request
┌──────────────────────────────▼────────────────────────────────────┐
│ LAYER 3 — FILE SYSTEM API / SYSCALL FACADE                        │
│   create() · open() · read() · write() · delete() · mkdir()       │
└─────────────┬──────────────────────────────────┬───────────────────┘
              │                                  │
┌─────────────▼────────────────────┐  ┌──────────▼──────────────────┐
│ LAYER 4A — RELIABILITY           │  │ LAYER 4B — STORAGE ENGINE    │
│   Journal (WAL) → Cache (LRU) →  │  │   FAT / Inode Allocator →    │
│   Compression → Versioning       │  │   Directory Mgmt →           │
│                                   │  │   Block Allocation → Defrag  │
└─────────────┬─────────────────────┘  └──────────┬───────────────────┘
              │                                  │
              └────────────────┬─────────────────┘
                                │ physical block I/O
┌──────────────────────────────▼────────────────────────────────────┐
│ LAYER 5 — VIRTUAL DISK STORAGE                                     │
│   Superblock | Free-Block Bitmap | FAT/Inode Table | Data Blocks   │
└──────────────────────────────┬────────────────────────────────────┘
                                │ raw metrics & events (async, non-blocking)
┌──────────────────────────────▼────────────────────────────────────┐
│ LAYER 6 — ANALYTICS & MONITORING DASHBOARD                         │
│   Disk usage · Fragmentation · Cache hit ratio · Quotas ·          │
│   Access logs · Journal/recovery events                            │
└─────────────────────────────────────────────────────────────────────┘
```

### Canonical Write Request Path (Pipeline A)

```
1. User Interface  --> sends write(file, data, session_token)
2. Authentication  --> validate session token & expiry; reject if expired/invalid
3. RBAC & Perms    --> verify role allows "write"; verify Unix rwx bits; reject if unauthorized
4. Quota Check     --> verify current usage + incoming size <= limit; reject if over
5. WAL Journal     --> append write intent record {op: WRITE, file, status: PENDING}; flush & fsync to disk
6. Compression     --> compress payload (zlib / RLE) BEFORE encryption
7. Encryption      --> encrypt compressed data with file key (AES-256 GCM)
8. Allocation      --> allocate free blocks in bitmap (FAT chain or Inode direct pointers)
9. Physical Write  --> write encrypted payload blocks to virtual disk image
10. Cache Update   --> insert/update written blocks in O(1) LRU cache
11. Versioning     --> snapshot new version entry
12. WAL Commit     --> append COMMITTED status record to journal log
13. Quota Update   --> update user's storage consumption
14. Analytics      --> emit event for live dashboard update
```

### Canonical Read Request Path (Pipeline B)

```
1. User Interface  --> sends read(file, session_token)
2. Authentication  --> validate session token & expiry
3. RBAC & Perms    --> verify role and rwx read permissions
4. LRU Cache       --> check cache:
                       HIT: serve data from memory cache
                       MISS: read blocks from disk -> Decrypt (AES-256) -> Decompress -> Cache put
5. Audit & Metrics --> log access attempt and emit hit/miss event
```

---

## 3. Core Data Structures & On-Disk Layout

Virtual disk configuration assumes a 4 KB block size and a 64 MB disk image (16,384 blocks) by default:

- **Superblock (Block 0):** `magic` (`"SMFS"`), `disk_size`, `block_size`, `total_blocks`, `free_blocks`, `allocation_mode` (`"FAT"` | `"INODE"`), `root_dir_ptr`, `fs_version`.
- **Free-Block Bitmap (Block 1):** 1 bit per block (0 = free, 1 = allocated).
- **FAT Table / Inode Table (Blocks 2–3):** `FAT_EOF` (-1), `FAT_FREE` (0), or next block cluster index in FAT mode; Direct block pointers (up to 12) + indirect pointer in Inode mode.
- **Directory Entries (Block 4):** Array of directory records mapping `name` -> `target` (inode ID or starting cluster), `entry_type` (`"file"` | `"dir"`), `size_bytes`, `mtime`, `perm_bits`, `owner_uid`.
- **Journal Log (WAL):** Append-only log storing `{txn_id, op_type, target, status, timestamp}`.
- **Version Store:** Per-file history array `{version_id, file_path, timestamp, block_map}`.
- **O(1) LRU Cache:** Hash map + doubly-linked list (`capacity`, `hits`, `misses`).

---

## 4. Complete Function & API Reference

### Storage Engine API
- `format_disk(path, size_bytes, block_size, mode)`: Formats virtual disk image, zeroes memory, writes superblock, bitmap, tables, and root directory.
- `mount_disk(path)`: Opens virtual disk image, reads superblock, and validates magic bytes `"SMFS"`.
- `allocate_block()`: Finds free block in bitmap, marks allocated, updates superblock, and emits usage metric.
- `allocate_blocks(n, strategy)`: Allocates `n` blocks using contiguous, linked, or indexed strategy.
- `free_block(block_id)`: Clears bitmap bit for block ID (idempotent).
- `fat_alloc_chain(n_blocks)`: Allocates `n_blocks` and links them in FAT table.
- `fat_free_chain(start)`: Traverses FAT chain from `start` to `FAT_EOF` and frees all blocks.
- `inode_allocate(owner_uid, perm_bits)`: Creates new inode entry.
- `inode_grow(inode_id, n_blocks)`: Allocates blocks and appends to direct/indirect pointers.
- `resolve_path(path)`: Resolves absolute path to target directory entry.
- `mkdir(path, owner_uid, perm_bits)`: Creates new directory entry in parent path.
- `rmdir(path)`: Removes empty directory (raises error if directory contains files).
- `list_dir(path)`: Returns list of active directory entries under path.
- `storage_create_file(path, owner_uid, perm_bits)`: Allocates metadata entry and directory record.
- `storage_write_file_blocks(path, data, size)`: Writes physical payload blocks to disk and updates pointers/mtime.
- `storage_read_file_blocks(path, out_data, out_size)`: Reads physical blocks from disk.
- `storage_delete_file(path)`: Frees block chains/inodes and deletes directory entry.
- `defragment(path)`: Re-allocates file blocks contiguously and invalidates stale cache entries.

### Security API
- `register_user(username, password, role)`: Generates per-user salt, hashes password with PBKDF2, and stores user.
- `hash_password(password, salt)`: Computes PBKDF2 HMAC-SHA256 password hash.
- `verify_password(password, stored_hash, salt)`: Constant-time password hash comparison.
- `authenticate(username, password)`: Verifies credentials and generates random session token.
- `validate_session(token)`: Verifies session token validity and expiration.
- `revoke_session(token)`: Explicit logout — deletes active session token.
- `check_rbac(role, operation, uid)`: Checks role against RBAC matrix.
- `check_permission_bits(perm_bits, owner_uid, requesting_uid, mode)`: Evaluates Unix 9-bit rwx permissions.
- `encrypt_data(plaintext, len, key, out_cipher)`: Encrypts data using AES-256 GCM authenticated cipher.
- `decrypt_data(ciphertext, len, key, out_plain)`: Decrypts AES-256 GCM ciphertext; raises error on tag mismatch.
- `log_access_attempt(uid, op, target, result)`: Appends record to security audit log and emits event.

### Reliability API
- `journal_write_intent(op_type, target)`: Writes PENDING WAL record and calls `fsync` to flush durably to disk.
- `journal_commit(txn_id)`: Writes COMMITTED record to WAL journal.
- `journal_rollback(txn_id)`: Writes ROLLED_BACK record to WAL journal.
- `replay_journal()`: Scans journal at boot, rolls back incomplete PENDING transactions, and reclaims orphaned blocks.
- `cache_get(block_id)`: Retrieves cached block data (O(1)) and marks most-recently-used.
- `cache_put(block_id, data)`: Inserts block into LRU cache; evicts tail if capacity exceeded.
- `cache_invalidate(block_id)`: Evicts block from cache when freed or overwritten.
- `compress_block(src, src_len, dst)`: Compresses data block (zlib / RLE).
- `decompress_block(src, src_len, dst)`: Decompresses data block.
- `create_version(file_path, block_map)`: Snapshots current block layout.
- `restore_version(file_path, version_id)`: Restores file to snapshot version layout.

### Integration API
- `check_quota(uid, incoming_bytes)`: Checks if write would exceed user limit.
- `quota_update(uid, delta_bytes)`: Updates user storage consumption.
- `emit_metric(event_type, payload_json)`: Non-blocking event emission to dashboard.
- `handle_write_request(path, data, token, fail_after)`: Layer 3 facade executing full Pipeline A.
- `handle_read_request(path, token)`: Layer 3 facade executing full Pipeline B.
- `handle_boot(disk_path)`: Mounts disk image and runs Pipeline C crash recovery.
- `run_benchmark(workload, num_ops)`: Drives performance comparison between FAT and Inode modes.

---

## 5. Critical Implementation Rules & Anti-Patterns To Avoid

1. **Permissions before Storage Mutation:** Always check authentication, RBAC, and permission bits before allocating blocks or modifying data structures.
2. **Quota before WAL Journal:** Verify storage quotas before writing journal intent records to avoid polluting the log with rejected operations.
3. **WAL Journal Flush before Disk Write:** Always flush and `fsync` the journal intent record to physical disk before touching data blocks or allocation tables.
4. **Compress before Encrypt:** Compress payload data before encryption on write (and decrypt before decompression on read); compressing high-entropy ciphertext yields 0% compression ratio.
5. **Cache Invalidation on Mutation:** Always invalidate stale LRU cache entries whenever a block is freed, overwritten, or defragmented.
6. **Non-blocking Metrics:** Wrap event emissions in error handlers so metrics logging never aborts or fails file system operations.

---

## 6. How to Build & Run

### Building & Running the C Implementation (C99 / GCC)

```bash
# 1. Build all executables and test suites
make all

# 2. Run unit, integration, and crash recovery test suites
./test_unit.exe
./test_integration.exe
./test_crash.exe

# 3. Format virtual disk (64 MB, 4096B blocks, FAT mode)
./m1_cli.exe format 64 4096 fat

# 4. Run interactive C CLI simulator
./smartfs.exe

# 5. Run live web dashboard server (http://localhost:5000)
./dashboard_server.exe
```

### Running the Python Implementation

```bash
# Set up Python virtual environment
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Format disk
python -m src.m1_storage.cli format --size 64M --block-size 4096 --mode fat

# Run Python simulator CLI
python -m src.main

# Run Python Web Dashboard (http://localhost:5000)
python -m dashboard.app

# Run pytest suite
pytest tests/unit tests/integration
python -m tests.crash_injection.run_all
```

---

## 7. Running SmartFS inside xv6 OS (Ubuntu QEMU)

SmartFS includes a dedicated self-contained C program `smartfs_xv6.c` designed to run natively inside **xv6 RISC-V / x86** under QEMU on Ubuntu:

```bash
# 1. Install prerequisites on Ubuntu
sudo apt update && sudo apt install -y build-essential gdb-multiarch qemu-system-misc gcc-riscv64-unknown-elf git

# 2. Clone xv6-riscv
git clone https://github.com/mit-pdos/xv6-riscv.git && cd xv6-riscv

# 3. Copy smartfs_xv6.c into xv6 user directory
cp /path/to/smartfs_xv6.c user/smartfs.c

# 4. Add $U/_smartfs\ to UPROGS in Makefile
# 5. Run in QEMU:
make qemu

# 6. Inside xv6 terminal prompt:
$ smartfs
```
