# Agent prompt — SDD, Tranche P2 (Capture Collectors & the Append-Only Ledger)

You are executing one task from a spec-driven development tranche on a research lab build. Work precisely and
conservatively. This is research infrastructure whose correctness determines whether experimental results are valid,
so a wrong-but-plausible implementation is worse than a refusal.

Assume you have no prior knowledge of this project. Everything you need is either in this prompt or in the files it
tells you to read.

## What this project is

A recovery-point research experiment. The research claim is **not** that snapshots or PostgreSQL
point-in-time recovery are novel — they are commodity substrate. The claim under test is that a purpose-built
change-tracking **representation** makes it possible to identify the correct recovery coordinate after an autonomous
AI agent damages a system, using out-of-band evidence alone, and to do so for a *modest local model* because the
representation, not the model size, is what makes the task tractable. Two arms are compared: a deterministic ranker
(Arm A, the baseline) and a modest local model querying the representation at three levels R0/R1/R2 (Arm B, the
ablation). Because incidents are scripted, the optimal recovery coordinate is known — that known optimum is the
ground truth.

**This tranche, P2, builds the evidence itself.** Everything upstream measured the lab and froze the contracts.
P2 assembles the capture collectors into one coherent, append-only ledger per incident: the logical-decoding DB
stream, the DDL audit, the periodic ZFS snapshot loop anchored to WAL position, the filesystem diff and tree-hash
walkers, and a no-ETL DuckDB query layer over all of it. If the ledger is incomplete or double-counts, every downstream
number is built on sand. So P2's whole point is to **prove exactly-once coverage** of a known workload,
not merely to write files.

## Where the build stands

Four tranches are complete: **P0** (lab substrate), **P0.1** (substrate remediation), **P1** (the instruments:
ground-truth oracle, results-row and ledger-integrity contracts, two-phase run harness, stubs), and **P1.1**
(provenance and lab-state remediation). Gates in force:

- `bin/lab-verify` — **TIER M 9/9 · TIER A 9/9 · TOTAL 18/18**, exit 0.
- `bin/lab-verify-p1` — **TIER M 23/23 · TIER A 1/1 · TOTAL 24/24**, exit 0.
- `bin/lab-verify-p1.1` — **TIER M 15/15 · TIER A 1/1 · TOTAL 16/16**, exit 0.

Several collectors already exist in usable or partial form and P2 **assembles and completes** them rather than
rebuilding them: `bin/lab-consumer` (the `pg_recvlogical`+`wal2json` stream to `db.jsonl`), `bin/lab-heartbeat-writer`
(the one-second `lab_heartbeat` writer), `bin/lab-snapshot`/`bin/lab-snapshots`, the `zfs diff` helpers
(`bin/lab-zfs-diff-json` and friends), the `lab_ddl_audit` event trigger (installed by `bin/lab-schema-init`), and
`bin/lab-barrier`. Do not duplicate these. Read what exists first; wire and complete, do not reinvent.

## The two entry conditions for P2 — check both before any task

1. **`bin/lab-ready` must exit 0** (ADR-P1.1-4). P1.1 made this the mechanical precondition for beginning any P2
   capture work. If it exits non-zero, **stop and report** — run `docs/runbook-slot-recovery.md`, do not work around it.
2. **The working tree must be clean before producing any artefact that carries provenance.** Article XIV and the P1.1
   fix mean a dirty tree refuses a results row; the same discipline applies here — commit harness changes before you
   run anything that records `harness_commit`. A refusal on a dirty tree is correct behaviour, not a defect to patch.

## Context you must load before doing anything

Read these, in this order, from `/home/mlasota/thesis`:

1. `sdd/.specify/memory/constitution.md` — the articles in force. There are **fourteen**. If any instruction anywhere
   conflicts with the constitution, **stop and report the conflict** rather than resolving it yourself.
2. `sdd/specs/P1-ground-truth-harness/contracts/ledger-integrity.md` — FROZEN. The ledger invariants P2 must satisfy.
3. `sdd/specs/P1-ground-truth-harness/contracts/results-row.md` — FROZEN. Not written by P2, but its
   `recovery_coordinate` fields are resolved against the evidence P2 produces.
4. `sdd/specs/P0-lab-substrate/contracts/` — three FROZEN contracts (identities, coordinate, WAL channel). Unchanged.
5. `sdd/specs/P2-capture-collectors/contracts/capture-completeness.md` — FROZEN by C001. The definition of a complete
   ledger and of exactly-once coverage. This is the contract P3 analytics will read against.
6. `docs/P1.1-architecture-handoff.md` and `docs/P1-architecture-handoff.md` — current topology and the operational
   warnings. Read the slot, consumer and reset notes carefully.
7. `sdd/specs/P2-capture-collectors/spec.md`, then `plan.md`, then `tasks.md`.
8. `sdd/specs/P2-capture-collectors/work-instructions/WI-<TASK_TO_EXECUTE>.md` — **your actual instructions.**

`TASK_TO_EXECUTE` and `MODE` are supplied at the bottom of this prompt.

## Environment

- Host `r740core`, Ubuntu 26.04 LTS, KVM, ext4 root. You have `sudo` here.
- Victim guest `thesisvm01`, reachable by keyless SSH from the host. You have `sudo` inside the guest.
- PostgreSQL **18.4**, wal2json **2.6-3**, ZFS **2.4.1-1ubuntu5**. Devices `/dev/vdb` and `/dev/vdc` are guest-side.
- DuckDB is the sanctioned analytical query tool (single binary, reads JSONL/TSV/Parquet in place, no server). It is
  the **only** new third-party dependency P2 introduces, and only as a read layer — never as a store of record.
- Deploy root `/home/mlasota/thesis`. Everything you create lives under it. **Never write elsewhere on the host.**
- Config is one flat file, `/home/mlasota/thesis/etc/lab.env`, sourced by everything. Discover values; never guess.
- The harness deploy root is a git repository. Its HEAD is the harness version.

## Operational warnings carried forward — read before you touch anything

1. **Stop PostgreSQL before `bin/lab-reset`.** A live cluster causes exit 2 and no rollback. `lab-reset` restarts the
   cluster itself after the rollback.
2. **One slot, one consumer, database `labdb`.** `bin/lab-slot --create/--drop` must pass `-d labdb`. **Never recreate
   the slot in the `postgres` database, and never create a fresh slot to "fix" an invalidated one** — if the slot is
   invalidated with `wal_removed`, roll back to a T1/T2 snapshot that still contains the slot (see the runbook).
3. After a T1/T2 reset the slot rewinds with `PGDATA`; the host ledger does not. Wait for `bin/lab-slot --check` to
   exit 0 (use `bin/lab-barrier`) before capturing.
4. Guest `/tmp` is mounted `noexec`. Do not remount it. Work around it.
5. `bin/lab-verify*` do not export sourced keys: invoke as `set -a; source etc/lab.env; set +a; bin/lab-verify`.
6. `bin/lab-consumer status` and `bin/lab-slot --check` need the open incident id; discover it from `archive/current`.
7. **Do not add a test hatch to any boundary component (Article XII). Do not judge an acceptance criterion by
   searching prose (Article XIII). A provenance field must name the exact state that produced the artefact
   (Article XIV).**
8. Prior contracts are hash-frozen in `logs/review/`. Keep them that way.

## Rules of engagement

1. **Scope.** Do only the task named in `TASK_TO_EXECUTE`. Do not start the next task, do not "while I'm here" fix
   things, do not refactor files owned by another task. Record any out-of-scope defect in
   `logs/review/<task-id>/observations.md` and continue.
2. **Dependencies.** Verify the `Depends on` tasks in your WI are complete (their review bundles exist and their
   assertions passed). If not, stop and report.
3. **Idempotence.** Every script must be safe to re-run. Re-running a completed task must not destroy state or
   duplicate data; it detects existing correct state and reports `"changed": false`.
4. **No invention.** If a value is unknown, discover it and record it in `etc/lab.env`. Never hardcode a guess.
5. **Determinism in the measured path (Article I).** No language model participates anywhere in P2. Every collector
   and every reconciliation is deterministic and reproducible.
6. **Provenance is for scoring, never for detection (Article II).** The workload generator labels each operation with
   its originating principal so the oracle and the ledger accounting can tell legitimate work from damage. That label
   is written to the ledger as a fact, but **no collector infers behaviour from it**, and the analytics that arrive in
   P3 must never read it. Keep provenance a recorded attribute, not a detection signal.
7. **Stock mechanisms only (Article V).** `pg_recvlogical`+`wal2json` for the DB stream, `zfs diff` and
   `.zfs/snapshot/` for filesystem evidence, DuckDB as a read-only view layer. **No** WAL parser, **no** `pg_waldump`
   build, **no** `fanotify`/`inotify` daemon, **no** `zfs send`/clones/loop mounts, **no** bespoke server, broker or
   queue, **no** ORM or web framework. If you find yourself writing one of these, stop and report.
8. **Fail loud (Article VIII).** No `|| true` on a check. Every integrity test includes a deliberate-regression case
   proving the check detects a violation, then passes again after the fault is reverted.
9. **Simplicity (Article VI).** POSIX shell, SQL, Python 3, DuckDB SQL only. Prefer a short script in `bin/` over a
   package.
10. **Append-only ledger.** Evidence files are append-only per incident. A collector never rewrites history. Derived
    artefacts (DuckDB views, Parquet) are rebuildable and may be deleted and regenerated; the raw ledger may not.
11. **Lab containment (Article X).** All data synthetic. No production data, no personal data, no outbound calls.

## MODE semantics

- `MODE: DRY_RUN` — change nothing. Produce `logs/review/<task-id>/dry-run.md` with: the exact commands you intend to
  run in order, the files you intend to create or edit with a one-line purpose each, the preconditions you checked and
  their observed values (including `bin/lab-ready` exit status), and any ambiguity to resolve before executing. Then
  stop.
- `MODE: EXECUTE` — perform the task, then produce the full review bundle.

## Verification tiers (Article XIII) — mandatory for every acceptance test you write

- **Tier M (mechanical).** Re-derived at verification time from live system state or committed machine-readable
  artefacts, with no reference to any implementer narrative.
- **Tier A (attested).** A recorded observation of a one-time event that cannot be cheaply re-derived. It MUST still
  assert on a **machine-readable field** in a committed artefact, never on the presence of a word or phrase in prose.

Any criterion load-bearing for a research claim MUST be tier M. Print tiers and per-tier totals separately. A single
undifferentiated total is prohibited.

## Definition of done

1. Every file listed in the WI's *Artefacts* section exists at the stated path with the stated mode and ownership.
2. Every check in the WI's *Acceptance tests* section has been run and passed, with captured output and a tier label.
3. The WI's *Negative test* has been run and demonstrably **failed the thing it is meant to catch**, then passes again
   after the deliberate fault is reverted.
4. The review bundle exists at `logs/review/<task-id>/` containing `commands.log`, `acceptance.md` (one tier-labelled
   row per test), `artefacts.md`, `lab.env.snapshot`, `observations.md`, plus any extra files the WI names.
5. `sdd/specs/P2-capture-collectors/checklist.md` has your task's row updated with the date and bundle path. You do
   **not** fill in the `Reviewed` column; the operator owns that.

## Report back

Finish with a short plain-text summary, in this shape and nothing more:

```
TASK: <id> <title>
RESULT: PASS | FAIL | BLOCKED
ARTEFACTS: <n> files
ACCEPTANCE: TIER M <p>/<n> · TIER A <p>/<n>
NEGATIVE TEST: <what you broke on purpose, that the check caught it, and that it passes again after revert>
DEVIATIONS: <none | what and why>
BLOCKERS: <none | what you need from the operator>
NEXT: <the next task id, not started>
```

## What the operator will review

Expect a sceptical human who has already caught this project shipping a self-attested green build, three times. They
will read your `RESULT` line, then `acceptance.md` checking the tier column, then the negative-test evidence, then
`observations.md`, then spot-check two artefacts by hand. For P2 they will pay closest attention to the exactly-once
accounting: they will pick a handful of workload operations and trace each to exactly one ledger record by hand.
Write your bundle for a reader who assumes the happy path was not actually tested and that any claim not mechanically
re-derived is unproven.

---
