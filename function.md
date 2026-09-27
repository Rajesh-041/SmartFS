# SmartFS — Function & API Reference

This is the authoritative list of functions each module exposes. Signatures are
given in Python-style pseudocode (per the recommended stack in `readme.md`);
adapt types if your team chooses C/Java, but **keep names and parameter order
identical** — this is the contract other modules code against.

Legend: **[pure]** = no side effects / no I/O. **[locks]** = acquires a
module-level lock (see `architecture.md §11`). **[emits]** = pushes a metrics
event to M4 on completion.

---

## 1. M1 — Storage Engine

### Disk & Format

**`format_disk(path: str, size_bytes: int, block_size: int, mode: str) -> Superblock`**
Creates `disk.img` of the given size, zeroes it, writes the superblock, an
all-free bitmap, an empty FAT or inode table (per `mode`), and a root
directory entry. Call once, before any other M1 function. Raises
`InvalidConfigError` if `size_bytes` is not a multiple of `block_size`.

**`mount_disk(path: str) -> Superblock`**
Opens an existing `disk.img`, reads and validates the superblock's magic
bytes and version. Raises `CorruptDiskError` on a bad magic number —
this should trigger `mistake.md §2`'s "never skip the magic check" rule.

### Allocation

**`allocate_block() -> int`** **[locks]** **[emits]**
Finds one free block via the bitmap, marks it allocated, emits a
`disk_usage_changed` event, and returns the block id. Raises `DiskFullError`
if none are free.

**`allocate_blocks(n: int, strategy: str = "linked") -> list[int]`** **[locks]**
Allocates `n` blocks using `"contiguous"`, `"linked"`, or `"indexed"`
strategy (see `design.md §3.3`). Returns block ids in write order.

**`free_block(block_id: int) -> None`** **[locks]** **[emits]**
Clears the bitmap bit for `block_id`. Idempotent — freeing an already-free
block is a no-op, not an error (avoids double-free crashes during recovery
replay).

**`find_free_blocks(n: int) -> list[int]`** **[pure]**
Read-only scan of the bitmap; used by planners/tests without mutating state.

### FAT Mode

**`fat_alloc_chain(n_blocks: int) -> int`**
Allocates `n_blocks`, links them in the FAT table, returns the starting
cluster. See `design.md §3.1`.

**`fat_free_chain(start: int) -> list[int]`**
Walks the chain from `start` to `FAT_EOF`, frees every block, returns the
freed ids (caller passes these to `free_block` for each, or this does it
internally — pick one and document it, don't do both).

**`fat_chain(start: int) -> list[int]`** **[pure]**
Returns the ordered list of block ids in the chain without mutating anything;
used by `read_file` and `defragment`.

### Inode Mode

**`inode_allocate() -> Inode`**
Creates a new inode with default owner/perm bits, no blocks yet.

**`inode_grow(inode: Inode, n_blocks: int) -> None`**
Allocates `n_blocks` and appends them to `inode.direct_blocks`, spilling
into an indirect block once the direct pointer limit is reached
(`design.md §3.2`).

**`inode_free(inode_id: int) -> list[int]`**
Frees the inode entry and every block it referenced (direct + indirect),
returns the freed block ids.

### Directory & Path

**`resolve_path(path: str) -> DirEntry | None`** **[pure]**
Splits `path` on `/`, walks each directory component from root, returns the
final `DirEntry` or `None` (caller raises `ENOENT`). Must handle `.` and `..`
consistently if your report claims full path semantics — otherwise document
the simplification explicitly.

**`mkdir(path: str, session: Session) -> None`**
Resolves the parent path, creates a new `Directory`/inode for the new
component, adds a `DirEntry` to the parent. Raises `ENOENT` if parent
missing, `EEXIST` if the name is already taken.

**`rmdir(path: str, session: Session) -> None`**
Removes an **empty** directory only; raises `ENOTEMPTY` otherwise. Never
silently recurse-delete — that's a separate, explicit operation if you add
one.

**`list_dir(path: str) -> list[DirEntry]`** **[pure]**

### File Operations (called by the Layer 3 API facade, not directly by UI)

**`create_file(path: str, session: Session) -> Inode | int`**
Allocates the metadata entry (inode or FAT starting cluster stub) and a
directory entry; does **not** allocate data blocks yet (empty file).

**`open_file(path: str, session: Session) -> FileHandle`**
Resolves the path, checks existence, returns an in-memory handle used by
subsequent `read_file`/`write_file` calls in the same session — this is
where you'd track an offset/cursor if supporting partial reads/writes.

**`read_file(handle: FileHandle) -> bytes`**
Retrieves the block chain (FAT or inode), reads blocks (through cache, see
M3), concatenates. This is the M1-owned tail end of Pipeline B — decryption
and decompression happen in M2/M3 *before* this returns to the caller, not
inside this function.

**`write_file(handle: FileHandle, data: bytes) -> int`**
The M1-owned tail end of Pipeline A: receives already-compressed,
already-encrypted bytes (compression/encryption happen upstream, see
`architecture.md §9`), allocates blocks, writes them, updates the directory
entry's size/mtime, returns bytes written.

**`delete_file(path: str, session: Session) -> None`**
Frees all blocks (via `fat_free_chain`/`inode_free`), removes the directory
entry. Must be journaled like a write (`architecture.md §9`).

**`truncate_file(path: str, new_size: int) -> None`**
Frees trailing blocks beyond `new_size`, updates size in metadata.

### Defragmentation

**`calculate_fragmentation(path: str = None) -> float`** **[pure]** **[emits]**
Returns fragmentation percentage for one file, or disk-wide if `path` is
omitted. Emits `fragmentation_reported`.

**`defragment(path: str) -> None`**
Implements `design.md §3.4`: journals itself as a transaction, rewrites the
file's blocks contiguously, updates pointers, frees old blocks.

---

## 2. M2 — Security

### Authentication

**`register_user(username: str, password: str, role: str) -> User`**
Generates a per-user salt, hashes the password (`hash_password`), stores the
`User` record. Raises `EUSEREXISTS` on duplicate username.

**`hash_password(password: str, salt: bytes) -> bytes`** **[pure]**
Wraps `bcrypt.hashpw` or `pbkdf2_hmac`. Never call `hashlib.sha256` alone —
see `mistake.md §3`.

**`verify_password(password: str, stored_hash: bytes, salt: bytes) -> bool`** **[pure]**
Constant-time comparison of the recomputed hash against `stored_hash`.

**`authenticate(username: str, password: str) -> Session`** **[emits]**
Looks up the user, calls `verify_password`; on success calls
`create_session`; on failure logs an audit entry (`log_access_attempt`) and
raises `EAUTHFAILED`. **Never** distinguish "wrong username" from "wrong
password" in the error message or timing (avoids username enumeration).

**`create_session(uid: int) -> Session`**
Generates a random token (`secrets.token_urlsafe(32)`), sets `expires_at`,
stores it server-side.

**`validate_session(token: str) -> Session`**
Looks up the token; raises `ESESSIONEXPIRED` or `ESESSIONINVALID`. Called on
**every** request, not just once at login (`design.md §4.2`).

**`revoke_session(token: str) -> None`**
Explicit logout — deletes the session record immediately, does not wait for
natural expiry.

### RBAC & Permissions

**`check_rbac(session: Session, operation: str) -> bool`** **[pure]** **[emits]**
Looks up the user's role in the RBAC matrix (`design.md §6`) for the given
operation class (`"read"`, `"write"`, `"admin"`). Logs the attempt either way.

**`check_permission_bits(inode: Inode, uid: int, mode: str) -> bool`** **[pure]**
Unix-style: compares `uid`/`gid` against the inode's owner/group, checks the
matching `rwx` triplet in `perm_bits` for `mode` ∈ {"r","w","x"}.

**`set_permission_bits(inode: Inode, new_bits: int, session: Session) -> None`**
Only the file's owner or an Admin role may call this successfully; enforced
via `check_rbac` + ownership check before mutation.

### Encryption

**`generate_key(uid: int, file_id: int) -> bytes`** **[pure]**
Derives a per-file key via HKDF from the user's session-held master key +
`file_id` (`design.md §6`).

**`encrypt_data(data: bytes, key: bytes) -> bytes`**
AES-GCM (or equivalent authenticated cipher) encryption; returns
ciphertext + nonce + auth tag packed together.

**`decrypt_data(ciphertext: bytes, key: bytes) -> bytes`**
Inverse of `encrypt_data`; raises `EDECRYPTFAILED` on auth-tag mismatch
(tampered or wrong key) — never return partially-decrypted bytes on failure.

**`rotate_key(uid: int) -> None`**
Re-derives and re-wraps stored per-file keys under a new master key (stretch
goal — document if not implemented rather than leaving it silently absent).

### Audit

**`log_access_attempt(uid: int, op: str, target: str, result: str) -> None`** **[emits]**
Appends `{uid, op, target, result, timestamp}` to the audit log and emits an
`access_logged` event for the dashboard.

---

## 3. M3 — Reliability

### Journaling

**`journal_write_intent(op_type: str, target: str, old_state: dict, new_state: dict) -> int`**
Appends a `PENDING` `JournalRecord`, **flushes to disk before returning**
(this synchronous flush is what makes the WAL guarantee real — an
in-memory-only "flush" defeats the entire subsystem, see `mistake.md §4`).
Returns `txn_id`.

**`journal_commit(txn_id: int) -> None`**
Appends a status-transition record marking `txn_id` as `COMMITTED`. Must be
called only after the corresponding disk mutation has fully completed.

**`journal_rollback(txn_id: int) -> None`**
Used both by explicit error handling mid-operation and by `replay_journal`
at boot; restores `old_state` and appends a `ROLLED_BACK` record.

**`scan_journal() -> list[JournalRecord]`** **[pure]**
Reads the full log in append order; used by `replay_journal`.

**`replay_journal() -> RecoveryReport`** **[emits]**
Implements `design.md §3.5`: for each `PENDING` record, rolls back (or
redoes, if that mode is enabled); for each `COMMITTED` record, verifies
consistency. Returns a report consumed by `mkdir`-boot logic and pushed to
the dashboard.

### Caching

**`cache_get(block_id: int) -> bytes | None`** **[locks]** **[emits]**
Returns cached data and marks it most-recently-used, or `None` on a miss
(caller falls through to disk). Emits `cache_hit`/`cache_miss`.

**`cache_put(block_id: int, data: bytes) -> None`** **[locks]**
Inserts/updates an entry; if at capacity, calls `evict()` first.

**`cache_evict() -> CacheEntry`** **[locks]**
Removes and returns the least-recently-used entry (tail of the linked list).

**`cache_invalidate(block_id: int) -> None`**
Must be called whenever a block is freed or overwritten out-of-band (e.g.
during defrag's pointer rewrite) — a stale cache entry after defrag is a
classic bug (`mistake.md §4`).

### Compression

**`compress_block(data: bytes) -> bytes`**
`zlib.compress`; called **before** encryption on write.

**`decompress_block(data: bytes) -> bytes`**
`zlib.decompress`; called **after** decryption on read.

### Versioning

**`create_version(file_path: str, block_map: list[int]) -> VersionEntry`**
Snapshots the current block layout as a new version (`design.md §2.7`).

**`list_versions(file_path: str) -> list[VersionEntry]`** **[pure]**

**`restore_version(file_path: str, version_id: int) -> None`**
Points the file's directory entry / inode back at the chosen version's
block map; should itself go through the journal (it's a mutation).

**`diff_versions(v1: int, v2: int) -> bytes`** **[pure]**
Optional/stretch: byte-level diff between two snapshots for reporting
"space saved" if diff-based storage is implemented later.

---

## 4. M4 — Integration, Quota & Analytics

### Quota

**`check_quota(uid: int, incoming_bytes: int) -> bool`** **[pure]**
Wraps `QuotaRecord.would_exceed`; called in Pipeline A step 4, **before**
`journal_write_intent`.

**`update_usage(uid: int, delta_bytes: int) -> None`** **[emits]**
Applied after a write/delete actually commits (positive delta for writes,
negative for deletes/truncation).

**`get_usage(uid: int) -> QuotaRecord`** **[pure]**

### Metrics / Event Bus

**`emit_metric(event_type: str, payload: dict) -> None`** **[emits]**
The single function every other module calls to reach the dashboard
(`design.md §7`). Must never raise — wrap internally in a try/except that
logs locally on failure, because a metrics bug must never fail a file
operation.

**`subscribe(event_type: str, handler: Callable) -> None`**
Registers a dashboard panel's update handler for a given event type
(Observer pattern, `design.md §8`).

### Orchestration (Layer 3 Facade)

**`handle_write_request(path: str, data: bytes, session: Session) -> Result`**
The actual implementation of Pipeline A end-to-end: calls M2 auth/RBAC/perm
checks → M4 quota check → M3 journal intent → M3 compress → M2 encrypt → M1
allocate+write → M3 cache update → M3 version snapshot → M3 journal commit →
M4 metrics emit. This is the one function that "knows" the full pipeline
order — every other function should only know its own step.

**`handle_read_request(path: str, session: Session) -> bytes`**
Implements Pipeline B end-to-end analogously.

**`handle_boot() -> None`**
Calls `mount_disk`, then `replay_journal` (Pipeline C), then starts accepting
requests. No request handling before recovery completes.

### Benchmarking & Reporting

**`run_benchmark(workload: str) -> BenchmarkResult`**
Drives a synthetic workload (sequential writes, random writes, mixed
read/write) against the current allocation mode; records throughput,
latency, fragmentation growth, cache hit ratio over time.

**`generate_report(results: list[BenchmarkResult]) -> str`**
Produces the FAT-vs-Inode comparison write-up content for the final report
(project plan §4 deliverable).

---

## 5. Cross-Module Call Rules (Quick Reference)

| If you are... | You may call... | You must NOT call... |
|---|---|---|
| M1 (Storage) | M3's `cache_get/put`, `compress/decompress`-adjacent data already prepared for you | M2's auth/RBAC directly (the facade already checked it) |
| M2 (Security) | Nothing from M1/M3 (security is a pure gate + crypto utility layer) | Any disk I/O directly |
| M3 (Reliability) | M1's block read/write primitives (to physically persist journal/cache) | M2's crypto (data arrives already encrypted/decrypted by the facade's ordering) |
| M4 (Integration) | Everything (it *is* the orchestrator) | Nothing forbidden, but must not reach into another module's private structs — only its public functions |

If you find yourself needing a function that isn't listed here, that's a
**Phase 1 interface gap** — raise it at the weekly sync (`workflow.md §5`)
and add it here before coding around it.
