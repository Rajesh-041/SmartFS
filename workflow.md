# SmartFS — Development Workflow

This maps the 16-week plan onto concrete engineering practice: branching,
review, testing gates, and phase exit criteria. The goal is that no phase ends
without evidence (tests, a demo, or a signed-off interface doc) that it's
actually done — "we ran out of time in Phase 3" is the single most common way
these projects fail (see `mistake.md §5`).

## 1. Shared Foundation (Week 0, Before Any Code)

Do this **together**, in one sitting, before splitting off:

1. Pick the language/stack (Python recommended — see `readme.md §3`).
2. Agree the virtual disk representation (`disk.img`, block size, default
   size) — write it into `config.yaml`.
3. Freeze the core data structures in `design.md §2` — every field name and
   type. Treat this file as reviewed and merged before Phase 2 starts.
4. Freeze the function signatures in `function.md` — this *is* the interface
   contract. Each member signs off on the functions their module exposes.
5. Set up the repo skeleton (`readme.md §4`), CI pipeline (§7 below), and the
   crash-injection harness stub (§6 below) so it exists from day one, not
   bolted on in Phase 5.

**Exit criterion:** `design.md` and `function.md` are merged to `main` and
every member has commented "agreed" on their module's section.

## 2. Git Branching Strategy

```
main                    — always green (CI passing), demo-able at any time
  └─ develop            — integration branch, merged into main at phase boundaries
       ├─ feature/m1-*  — M1's work (e.g. feature/m1-fat-allocator)
       ├─ feature/m2-*  — M2's work
       ├─ feature/m3-*  — M3's work
       └─ feature/m4-*  — M4's work
```

- Branch names: `feature/<module>-<short-description>`, e.g.
  `feature/m3-journal-wal`.
- Commit messages: `<module>: <imperative summary>` — e.g.
  `m1: implement contiguous block allocation strategy`.
- No one commits directly to `develop` or `main`; everything goes through a
  pull request, even solo work — this creates a paper trail for the report.
- Rebase feature branches onto `develop` before opening a PR; merge commits
  only at `develop -> main`.

## 3. Pull Request & Code Review

Every PR must include:
- [ ] Which function(s) from `function.md` this implements (link the section)
- [ ] Unit tests for the new code, passing locally
- [ ] Any deviation from the agreed signature, called out explicitly with
      reasoning — not silently shipped
- [ ] Updated docstrings if behavior differs from `function.md`'s description

Review checklist (reviewer, not author, checks these):
- Does this respect the ordering rules in `architecture.md §9` (e.g., does a
  write path really check quota before journaling)?
- Are locks acquired/released correctly around shared structures (bitmap,
  cache, journal)? (`architecture.md §11`)
- Are error paths tested, not just the happy path? (`mistake.md §6`)
- Is anything security-sensitive (passwords, keys) logged in plaintext
  anywhere, including in test output? (`mistake.md §3`)

One other team member must approve before merge to `develop`. For merges from
`develop` to `main` at a phase boundary, **all four** members approve.

## 4. Local Development Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt   # pytest, black, ruff/flake8, mypy

pre-commit install                      # runs lint + format on every commit
```

Each module owner works against **mocked/stubbed versions** of the other
three modules' interfaces during Phase 2 (see `function.md` for exact
signatures to stub), so no one blocks on someone else's unfinished code:

```python
# tests/unit/m1/conftest.py
class FakeSecurity:
    def check_permission_bits(self, *a, **kw): return True
class FakeReliability:
    def journal_write_intent(self, *a, **kw): return 1
    def cache_get(self, *a, **kw): return None
```

This is what makes Phase 2's "build independently against agreed interfaces"
actually work — without stubs, everyone is implicitly waiting on everyone
else, and Phase 3 discovers the mismatches all at once.

## 5. Weekly Sync (Every Phase, Non-Negotiable)

30–45 minutes, same time every week. Agenda:

1. Each member demos their module's *current* API against real (not mocked)
   calls where possible — this is the single highest-leverage practice for
   catching interface drift early (project plan §8 recommendation).
2. Any function signature that changed since last week is flagged and
   updated in `function.md` in the same meeting, not "later."
3. Blockers: anyone stuck on a cross-module dependency says so out loud, not
   in a side channel three days later.
4. Update a shared burndown/status board (even a simple table in the repo
   wiki) — Phase 3's integration plan depends on knowing real status, not
   optimistic status.

## 6. Testing Workflow

### 6.1 Unit Tests (owned per-module, run continuously)

Each module's `tests/unit/<module>/` covers its own functions in isolation
using the stubs from §4. Minimum bar per module:

- **M1:** disk full, fragmented allocation, deep directory nesting, chain
  traversal correctness (FAT and Inode), orphan detection.
- **M2:** wrong password, expired session, permission-denied on every rwx
  combination, RBAC-denies-but-bits-allow and vice versa, encrypt/decrypt
  round-trip, tampered ciphertext rejection.
- **M3:** journal record round-trip, LRU eviction order correctness,
  compress/decompress round-trip, version snapshot/restore correctness.
- **M4:** quota boundary (`used + incoming == limit` exactly), quota
  rejection, metrics emission never raises even if a handler throws.

### 6.2 Integration Tests (Phase 3 onward)

Real modules, no stubs, run against a scratch `disk.img`:

- Full Pipeline A trace: login → mkdir → write → read back → verify bytes.
- Full Pipeline B: cache miss then hit, verify hit-ratio metric changes.
- Cross-module scenario from the project plan: *"User A creates file →
  encrypts → system crashes → recovers → dashboard reflects updated state."*

### 6.3 Crash-Injection Testing (build the harness in Week 0, exercise it hard in Phase 5)

```bash
python -m tests.crash_injection.run --fail-after journal
python -m tests.crash_injection.run --fail-after allocate
python -m tests.crash_injection.run --fail-after physical_write
python -m tests.crash_injection.run --fail-after commit
```

Each run: kill the process at the named point (`design.md §3.6`), restart,
run `replay_journal`, then assert:
1. The bitmap/FAT/inode tables are internally consistent.
2. No orphaned blocks remain allocated but unreferenced.
3. The file is in exactly the pre-write or exactly the post-write state —
   never a partial/corrupted middle state.

### 6.4 CI Pipeline (runs on every PR)

```
lint (ruff/flake8) -> type-check (mypy, optional) -> unit tests (per module)
   -> integration tests (Phase 3+) -> crash-injection suite (Phase 5+)
```

`main` must stay green. If CI is red, the next PR is a fix, not a feature.

## 7. Phase-by-Phase Plan (16 Weeks)

| Phase | Weeks | Focus | Exit Criteria |
|---|---|---|---|
| 1 — Design | 1–2 | Architecture, data structures, module interfaces | `design.md` + `function.md` merged and signed off by all four |
| 2 — Core Build | 3–7 | Each member builds their module against stubs | Each module's unit tests green; module demoable in isolation via CLI stub harness |
| 3 — Integration | 8–10 | Combine modules, resolve interface mismatches, end-to-end flows | Pipeline A and B integration tests green with **real** modules, no stubs remaining |
| 4 — Advanced Features | 11–12 | Crash simulation, defrag, encryption hardening, dashboard polish | Pipeline C and D integration tests green; dashboard shows all six panels live |
| 5 — Testing & Hardening | 13–14 | Stress tests, crash injection, security tests | Crash-injection suite (§6.3) green for all four failure points; security test checklist (`mistake.md §3`) reviewed |
| 6 — Docs & Demo | 15–16 | Report, presentation, final demo prep | Deliverables checklist (`readme.md §7`) fully checked; demo script (§9 below) rehearsed at least twice |

**Do not compress Phase 3.** Every retrospective on projects like this one
names "we didn't leave enough integration time" as the top regret — see
`mistake.md §5`.

## 8. Risk & Blocker Escalation

- A blocker that isn't resolved within 2 working days gets raised at the next
  weekly sync explicitly, with the blocking function/interface named.
- If a module owner is behind schedule at the Phase 2→3 boundary, the team
  reduces scope (drop a stretch goal like key rotation or diff-based
  versioning) rather than skip integration testing to make up time.
- Interface changes discovered during Phase 3 get a same-day update to
  `function.md`, plus a one-line note in the PR that touches it — don't let
  the doc drift from the code.

## 9. Demo Day Workflow

1. Boot the simulator from a fresh `disk.img` on stage/screen-share (not a
   pre-warmed one — shows format + mount working).
2. Log in as two different roles (admin, standard) to show RBAC live.
3. Write a file, show the dashboard's disk usage and quota panels update.
4. **Live crash-and-recover demo** — kill the process mid-write, restart, show
   the recovery report and the file's correct final state. The project plan
   flags this as the most impressive moment; do not cut it for time.
5. Trigger defrag, show the fragmentation metric before/after.
6. Close with the FAT-vs-Inode benchmark comparison chart.

Rehearse this exact sequence at least twice before the real demo — live crash
demos are exactly the kind of thing that reveals an untested edge case at the
worst possible moment if you haven't run it end-to-end beforehand.
