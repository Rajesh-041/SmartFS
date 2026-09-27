# SmartFS — Mistakes To Avoid

Read your module's section **before** you start coding, not after something
breaks. Every item here maps back to a specific rule in `architecture.md`,
`design.md`, or `function.md` — that reference is included so you can see the
correct behavior, not just the wrong one.

## 1. Architectural / Ordering Mistakes (Everyone)

- **Don't check permissions after touching storage.** If auth/RBAC/permission
  checks happen after allocation or a partial write, an unauthorized request
  has already caused side effects before being rejected. Order must be exactly
  Auth → RBAC → Permission bits → Quota → Journal → ... (`architecture.md §9`).
- **Don't journal before checking quota.** Logging an operation that will be
  rejected anyway pollutes the log and complicates recovery reasoning for no
  benefit.
- **Don't write to disk before the journal entry is durably flushed.** This
  single ordering inversion silently destroys the crash-recovery guarantee —
  a crash between disk-write and journal-write leaves no record to detect or
  undo it. This is the most important rule in the entire project; if you
  remember only one thing from this file, remember this one.
- **Don't compress after encrypting.** Encrypted output is high-entropy and
  essentially incompressible — doing this doesn't error, it just silently
  produces near-zero compression savings, which is a bug that only surfaces
  weeks later when someone asks "why doesn't compression do anything?"
  (`architecture.md §9`). Order is compress → encrypt on write, decrypt →
  decompress on read.
- **Don't make the Analytics layer synchronous.** If any module's write path
  calls into the dashboard and *waits* for it, a slow or buggy dashboard
  render now slows down or can crash every file operation. Metrics emission
  must be fire-and-forget and must never raise (`function.md §4`,
  `emit_metric`).
- **Don't let modules reach into each other's internal data structures.**
  M1 reading M3's cache's internal linked-list node directly (instead of
  calling `cache_get`) looks like a shortcut in week 4 and becomes an
  unfixable coupling bug in week 9. Only call the functions in `function.md`.

## 2. Storage Engine Mistakes (M1)

- **Don't forget to update the bitmap and the FAT/inode table together.**
  If a crash (or a bug) leaves the bitmap saying "allocated" while the
  FAT/inode chain doesn't reference the block (or vice versa), you have a
  silent corruption that only recovery's orphan scan should be catching —
  don't let normal-path code produce this state in the first place.
- **Don't skip the disk-full case.** `allocate_block` must raise a clear
  `DiskFullError`, not silently wrap around, return `-1`, or corrupt the
  bitmap by writing past `total_blocks`.
- **Don't leave the directory entry stale after a write.** Size and mtime on
  the parent directory entry (or inode) must be updated as part of the same
  write operation — a `read_file` that trusts a stale size will truncate or
  overread.
- **Don't implement `resolve_path` as "just split on `/` and hope."** Handle
  a missing intermediate directory (`ENOENT`), a component that names a file
  instead of a directory, and don't crash on a trailing slash or a bare `/`.
- **Don't allocate blocks without holding the allocator lock.** Two
  concurrent `allocate_block()` calls without a lock can hand out the same
  block id to two different files — this is a classic race condition and
  the whole reason `architecture.md §11` specifies a single allocator lock.
- **Don't treat defrag as exempt from journaling.** "It's just a background
  maintenance task" is exactly how a crash mid-defrag turns into permanent
  data loss. Defrag is a transaction like any write (`design.md §3.4`).

## 3. Security Mistakes (M2)

- **Don't hash passwords with plain `sha256(password)`.** No salt, no
  iteration count — this is crackable in seconds with a rainbow table. Use
  `bcrypt` or PBKDF2 with a per-user salt and a real iteration count
  (`design.md §6`).
- **Don't use one global salt for every user.** That defeats the entire
  purpose of salting — it's the same as using no salt against a
  precomputed-for-this-salt attack.
- **Don't skip session expiry checks on every request.** Validating the
  token only at login and then trusting it forever means a stolen or
  leaked token never expires. `validate_session` must run on every request
  (`function.md §2`).
- **Don't check RBAC *or* permission bits — check both.** RBAC answers "can
  this role ever do this," permission bits answer "does this file allow it
  for this user." A Standard user with world-writable file permissions still
  shouldn't be able to write someone else's file if RBAC says Standard users
  only write their own — passing one check is not a substitute for the
  other (`design.md §6`).
- **Don't hardcode encryption keys or derive them from a fixed constant.**
  If every file (or every user) ends up with the same effective key because
  the derivation ignores `file_id`/`uid`, encryption is providing no real
  isolation between users' data.
- **Don't return partially-decrypted data on an auth-tag failure.** If the
  ciphertext was tampered with or the wrong key was used, fail closed and
  raise — never hand back whatever bytes came out of the cipher.
- **Don't log passwords, raw keys, or full session tokens in the audit log
  or in debug output.** Log the *fact* of an access attempt and its result,
  never the secret material itself — including in test fixtures and CI logs.
- **Don't let a failed login reveal whether the username exists.** "Unknown
  user" vs. "wrong password" as different error messages (or different
  response timing) enables username enumeration; return one generic
  `EAUTHFAILED` either way.

## 4. Reliability Mistakes (M3)

- **Don't let "flush the journal" mean "write it to an in-memory buffer."**
  If the journal entry isn't actually durable on disk before the operation
  proceeds, a crash at that exact moment defeats the WAL guarantee even
  though the code *looks* correct. Verify this with an actual crash-injection
  test (`workflow.md §6.3`), not just a code read-through.
- **Don't let the journal grow forever with no checkpointing plan.** For a
  semester project this can stay simple, but document the limitation rather
  than silently letting `scan_journal()` get slower every week of the demo.
- **Don't forget to invalidate the cache after defrag or delete.** A block
  that's been freed and reallocated to a different file, while a stale
  cache entry for the old file/block mapping still exists, will silently
  serve wrong data on the next read. Every code path that changes what a
  block id "means" must call `cache_invalidate` (`function.md §3`).
- **Don't implement LRU with a plain list and linear-scan "most recently
  used" tracking "for simplicity."** It will pass small tests and then be
  the reason your benchmark numbers in Phase 5 look wrong under any
  realistic cache size — implement the O(1) dict + doubly-linked-list
  version from the start (`design.md §2.8`).
- **Don't attempt diff-based versioning before snapshot-based versioning has
  passing tests.** Diffs add a second failure mode (a corrupt diff chain)
  on top of one you haven't proven solid yet. Ship snapshots first
  (`design.md §5`).
- **Don't test crash recovery only against a "friendly" crash point.**
  Killing the process only *after* the journal write but *before* the disk
  write is the easy case. Also test killing it mid-physical-write and
  between physical-write and journal-commit (`function.md §3`,
  `workflow.md §6.3`) — these are the cases that actually distinguish a
  correct undo-log implementation from a lucky one.

## 5. Integration & Project-Management Mistakes (Everyone, M4 especially)

- **Don't start Phase 2 without a signed-off `function.md`.** Building
  against a signature you assume rather than one the team agreed on is the
  single biggest source of Phase 3 rework. If a function doesn't exist yet
  in the doc, add it and get a nod before coding around it.
- **Don't skip stub/mock implementations during Phase 2.** Without them,
  every module owner is implicitly blocked on every other module's
  progress, and integration becomes a big-bang event in week 8 instead of
  a continuous process (`workflow.md §4`).
- **Don't compress Phase 3 (Integration) to "make up time."** This is the
  single most commonly regretted decision on projects with this exact
  shape — a module that looks "done" in isolation reliably surfaces 3–5
  real interface mismatches once it talks to the other three for real.
  Protect this phase's time budget before anything else.
- **Don't let interface changes discovered mid-project go undocumented.**
  If M3 changes a function's return type during Phase 3 and tells M1 in a
  hallway conversation but never updates `function.md`, the next person to
  touch that code (including you, in week 14) will implement against the
  stale doc.
- **Don't let one module become a silent bottleneck.** If the weekly sync
  (`workflow.md §5`) reveals someone is two weeks behind, the right response
  is scope reduction (cut a stretch goal) — not everyone else waiting
  quietly until Phase 5.
- **Don't skip code review "because we're a small team and trust each
  other."** The review checklist in `workflow.md §3` exists specifically to
  catch ordering violations (§1 above) that are easy to introduce and hard
  to spot in your own code.

## 6. Testing Mistakes (Everyone)

- **Don't test only the happy path.** "It works when the user is logged in,
  has permission, and there's enough quota and disk space" is necessary but
  nowhere near sufficient — every rejection path (`EAUTHFAILED`,
  `PermissionDenied`, `QuotaExceeded`, `DiskFullError`, `ENOENT`) needs its
  own test.
- **Don't test permission logic with only one role.** Test Admin, Standard,
  and Guest against the full RBAC matrix (`design.md §6`), including cases
  where RBAC and permission bits disagree.
- **Don't skip concurrent-access tests just because the simulator is mostly
  single-threaded in the demo.** At minimum, test that two allocation calls
  in quick succession never return the same block id.
- **Don't test only with tiny toy files.** Fragmentation, indirect-block
  behavior, and cache eviction under pressure only show up with files large
  enough to actually stress the block/indirect-pointer limits and the
  cache's configured capacity.
- **Don't treat the crash-injection suite as optional "if there's time" work
  in Phase 5.** It is the direct evidence for the project's most important
  claim (crash recovery works) and for the demo's centerpiece moment
  (`workflow.md §9`).

## 7. Documentation & Demo Mistakes

- **Don't leave known limitations undocumented.** If key management isn't
  hardware-backed, if diff-based versioning wasn't implemented, if
  concurrency is simplified — say so explicitly in the report. A reviewer
  who discovers an undocumented gap trusts the rest of the report less; one
  who reads "we chose X over Y because Z, and here's what that trades away"
  trusts it more.
- **Don't skip rehearsing the live crash-and-recover demo.** It is
  explicitly called out as the most impressive moment in the project plan —
  and live demos are exactly where an untested edge case (a leftover debug
  flag, a stale `disk.img` from a previous run) will surface if you haven't
  run the exact sequence beforehand at least twice.
- **Don't let the report's architecture description drift from the actual
  code.** If `architecture.md` says compression happens before encryption
  but a late refactor reversed it without updating the doc, that
  inconsistency is the first thing a careful reader (or grader) will catch.
