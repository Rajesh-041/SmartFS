# SmartFS — A Secure and Intelligent File System Simulator

SmartFS is a simulated file system built to demonstrate, in working code, the core
subsystems of a real OS storage stack: allocation and directory management, access
control and encryption, write-ahead logging and crash recovery, caching and
versioning, and a live analytics/quota layer that ties everything together.

It is built by a 4-person team, each owning one subsystem end-to-end (design, code,
tests, docs), integrating into a single simulator with one command flow: a user logs
in → browses files → performs operations → sees the effect on disk *and* on a live
dashboard.

This repository's documentation set:

| File | Purpose |
|---|---|
| `readme.md` | This file — overview, setup, usage |
| `architecture.md` | Layered system architecture, data flow pipelines, module ownership |
| `design.md` | Low-level design: data structures, algorithms, state machines, design patterns |
| `function.md` | Full function/API reference for all four modules |
| `workflow.md` | Team development workflow, git strategy, phase-by-phase plan, CI/testing |
| `mistake.md` | Known pitfalls and anti-patterns — read before you implement, not after |

---

## 1. What SmartFS Does

- **Multi-user login** with hashed passwords, sessions, and role-based access control
  (Admin / Standard / Guest)
- **Unix-style permission bits** (owner/group/others, r/w/x) enforced per file
- **Two selectable allocation strategies** — FAT-style chaining and Inode-style
  indexed allocation — switchable via config, for direct comparison
- **Nested directories** with full path resolution (`/home/user/file.txt`)
- **Write-ahead journaling** so every mutating operation is crash-safe
- **Crash recovery** that replays or rolls back incomplete operations on restart
- **File versioning** — snapshot-based rollback to any prior save
- **Transparent compression and encryption** on the write path (and their inverse on
  read), in the order that keeps both effective (see `architecture.md §9`)
- **LRU block/file cache** with live hit/miss ratio
- **Per-user storage quotas** enforced before any block is allocated
- **Background/on-demand defragmentation** with before/after fragmentation metrics
- **Real-time analytics dashboard**: disk usage, fragmentation, cache ratio, quota
  usage, access logs, journal/recovery events

## 2. Team & Ownership

| Member | Role | Owns |
|---|---|---|
| M1 | Storage Engine Lead | FAT/Inode allocation, directory mgmt, block allocation, defrag |
| M2 | Security Lead | Auth, RBAC, permission bits, encryption |
| M3 | Reliability Lead | Journaling, crash recovery, versioning, compression, cache |
| M4 | Integration & Analytics Lead | Quota, dashboard, integration glue, benchmarking, testing |

Each module is developed against **agreed interface contracts** (see `design.md §9`)
so the four subsystems can be built in parallel and integrated with minimal rework.

## 3. Tech Stack

- **Language:** Python 3.11+ (recommended for the semester timeline — fast to
  build, rich stdlib for hashing/zlib; a C variant is documented as an optional
  stretch goal for OS-realism)
- **Encryption:** `cryptography` (AES-GCM) or `PyCryptodome`
- **Compression:** `zlib` (stdlib)
- **Password hashing:** `bcrypt` (preferred) or `hashlib.pbkdf2_hmac` with per-user salt
- **Virtual disk:** a single binary file (`disk.img`), fixed-size blocks, accessed
  via `seek`/`read`/`write`
- **Dashboard:** Flask + Chart.js (web) — Tkinter/PyQt is an acceptable fallback
- **Testing:** `pytest`, plus a crash-injection harness (see `workflow.md §6`)

## 4. Project Layout

```
smartfs/
├── disk.img                  # the virtual disk (generated, not committed)
├── config.yaml                # block size, allocation mode (FAT|INODE), quotas
├── src/
│   ├── m1_storage/            # allocator, directory mgmt, defrag
│   ├── m2_security/           # auth, rbac, permissions, crypto
│   ├── m3_reliability/        # journal, recovery, cache, versioning, compression
│   ├── m4_integration/        # quota, dashboard, orchestration/CLI glue
│   └── common/                # shared structs, error types, interface contracts
├── tests/
│   ├── unit/                  # per-module unit tests
│   ├── integration/           # cross-module end-to-end tests
│   └── crash_injection/       # kill-and-recover test harness
├── docs/                       # this documentation set
└── dashboard/                  # Flask app + static assets
```

## 5. Getting Started

```bash
# clone and set up
git clone <repo-url> smartfs && cd smartfs
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# create and format the virtual disk (default 64 MB, 4 KB blocks, FAT mode)
python -m src.m1_storage.cli format --size 64M --block-size 4096 --mode fat

# run the simulator CLI
python -m src.main

# run the dashboard (separate terminal)
python -m dashboard.app          # http://localhost:5000

# run tests
pytest tests/unit
pytest tests/integration
python -m tests.crash_injection.run_all
```

## 6. Example Session

```text
> login alice ********
[OK] session token 8f2a...  role=standard

> mkdir /home/alice/projects
[OK]

> write /home/alice/projects/notes.txt "hello smartfs"
[JOURNAL] WRITE PENDING -> COMMITTED
[OK] 13 bytes written, quota: 13/10485760

> read /home/alice/projects/notes.txt
hello smartfs

> simulate-crash --during write
[SIMULATED CRASH]
> restart
[RECOVERY] scanning journal... 1 PENDING entry found -> rolled back
[RECOVERY] bitmap/FAT re-validated, 0 orphaned blocks reclaimed
[OK] system clean, resuming
```

## 7. Deliverables Checklist

- [ ] Working simulator, all four modules integrated
- [ ] Source code with clear module boundaries and documented interfaces
- [ ] Unit + integration + crash-injection test suites (green in CI)
- [ ] Analytics dashboard (live demo + screenshots)
- [ ] Live crash-recovery demonstration
- [ ] Project report (architecture, OS concepts implemented, design decisions)
- [ ] Final presentation / demo script (see `workflow.md §9`)

## 8. Where To Go Next

- New to the codebase? Read `architecture.md` first, then `design.md`.
- Implementing a function? Check `function.md` for the agreed signature *before*
  you write it — mismatches here are the #1 cause of late integration pain.
- About to start coding? Skim `mistake.md` for your module's section first.
- Planning your week? `workflow.md` maps every phase to concrete exit criteria.
