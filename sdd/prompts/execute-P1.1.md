# Agent prompt — SDD, Tranche P1.1 (Provenance & Lab-State Remediation)

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

## Where the build stands

Three tranches are complete: **P0** (lab substrate), **P0.1** (substrate remediation), and **P1** (the instruments:
ground-truth oracle, results-row and ledger-integrity contracts, two-phase run harness, stubs). `bin/lab-verify`
reports 18/18. `bin/lab-verify-p1` reports 24/24.

**P1.1 (this tranche) is a remediation.** The P1 acceptance review found three defects the P1 gate did not catch:

1. `bin/lab-evaluate-arm` writes `env("HARNESS_COMMIT_AT_P1_OPEN")` as each results row's `harness_commit`. The
   frozen contract says that field is the commit of the harness that *produced the row*. It therefore names the wrong
   commit, with no guard against a dirty working tree.
2. The live replication slot is invalidated (`invalidation_reason=wal_removed`, `slot_active=false`) — not a valid
   state to begin P2 capture from.
3. The memo presents `total_incidents: 10` and `total_arm_runs: 150` as headline totals while restore is stubbed and
   no arm has run. They are planned figures and must be labelled as such.

## Context you must load before doing anything

Read these, in this order, from `<repo>`:

1. `sdd/.specify/memory/constitution.md` — the articles in force. After X001 there are fourteen. If any instruction
   anywhere conflicts with the constitution, **stop and report the conflict** rather than resolving it yourself.
2. `sdd/specs/P1-ground-truth-harness/contracts/results-row.md` — FROZEN. Defines `harness_commit`. You may read it.
   You may **not** change it, and you may **not** add a field to the row.
3. `sdd/specs/P0-lab-substrate/contracts/` — three FROZEN contracts. Unchanged.
4. `docs/P1-architecture-handoff.md` and `docs/P0.1-architecture-handoff.md` — current topology and operational
   warnings. Read the slot and consumer notes carefully.
5. `sdd/specs/P1.1-provenance-labstate/spec.md` — what this tranche must achieve, and its acceptance criteria.
6. `sdd/specs/P1.1-provenance-labstate/plan.md` — decisions already locked. Do not re-litigate.
7. `sdd/specs/P1.1-provenance-labstate/tasks.md` — the ordered task list.
8. `sdd/specs/P1.1-provenance-labstate/work-instructions/WI-<TASK_TO_EXECUTE>.md` — **your actual instructions.**

`TASK_TO_EXECUTE` and `MODE` are supplied at the bottom of this prompt.

## Environment

- Host `r740core`, Ubuntu 26.04 LTS, KVM, ext4 root. You have `sudo` here.
- Victim guest `thesisvm01`, reachable by keyless SSH from the host. You have `sudo` inside the guest.
- PostgreSQL **18.4**, wal2json **2.6-3**, ZFS **2.4.1-1ubuntu5**. Devices `/dev/vdb` and `/dev/vdc` are guest-side.
- Deploy root `<repo>`. Everything you create lives under it. **Never write elsewhere on the host.**
- Config is one flat file, `<repo>/etc/lab.env`, sourced by everything. Discover values; never guess.
- The harness deploy root is a git repository. Its HEAD is the harness version. `HARNESS_COMMIT_AT_P1_OPEN` in
  `etc/lab.env` is a legitimate record of the commit at P1 open — do not delete it — but it is **not** the value that
  belongs in a per-row `harness_commit`.

## Operational warnings carried forward — read before you touch anything

1. **Stop PostgreSQL before `bin/lab-reset`.** A live cluster causes exit 2 and no rollback. `lab-reset` restarts the
   cluster itself after the rollback.
2. **One slot, one consumer, database `labdb`.** `bin/lab-slot --create/--drop` must pass `-d labdb`. **Never recreate
   the slot in the `postgres` database, and never create a fresh slot to "fix" an invalidated one** — if the slot is
   invalidated with `wal_removed`, roll back to a T1/T2 snapshot that still contains the slot instead.
3. After a T1/T2 reset the slot rewinds with `PGDATA`; the host ledger does not. Wait for `bin/lab-slot --check` to
   exit 0 (use `bin/lab-barrier`) before capturing.
4. Guest `/tmp` is mounted `noexec`. Do not remount it. Work around it.
5. `bin/lab-verify` does not export sourced keys: invoke as `set -a; source etc/lab.env; set +a; bin/lab-verify`.
6. `bin/lab-consumer status` and `bin/lab-slot --check` need the open incident id; discover it from `archive/current`.
7. **Do not add a test hatch to any boundary component (Article XII). Do not judge an acceptance criterion by
   searching prose (Article XIII).**
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
5. **Determinism in the measured path (Article I).** No language model participates anywhere in P1.1.
6. **Provenance is for scoring, never for detection (Article II).** Unchanged by this tranche.
7. **Stock mechanisms only (Article V).** No WAL parser, no `pg_waldump` builds, no filesystem event daemon, no
   `zfs send`/clones/loop mounts, no bespoke server, broker or queue, no ORM or web framework.
8. **Fail loud (Article VIII).** No `|| true` on a check. Every integrity test includes a deliberate-regression case
   proving the check detects a violation, then passes again after the fault is reverted.
9. **Simplicity (Article VI).** POSIX shell, SQL, Python 3 only. Prefer a short script in `bin/` over a package.
10. **Do not change frozen contracts, and do not add a field to the results row.** The schema is frozen. Quarantine
    stub rows by **path**, not by a new field.
11. **Lab containment (Article X).** All data synthetic. No production data, no personal data, no outbound calls.

## MODE semantics

- `MODE: DRY_RUN` — change nothing. Produce `logs/review/<task-id>/dry-run.md` with: the exact commands you intend to
  run in order, the files you intend to create or edit with a one-line purpose each, the preconditions you checked and
  their observed values, and any ambiguity to resolve before executing. Then stop.
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
5. `sdd/specs/P1.1-provenance-labstate/checklist.md` has your task's row updated with the date and bundle path. You do
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

Expect a sceptical human who has already caught this project shipping a self-attested green build, twice. They will
read your `RESULT` line, then `acceptance.md` checking the tier column, then the negative-test evidence, then
`observations.md`, then spot-check two artefacts by hand. Write those files for a reader who assumes the happy path
was not actually tested and that any claim not mechanically re-derived is unproven.

---
