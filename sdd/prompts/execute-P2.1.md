# Agent prompt — SDD, Tranche P2.1 (Reconciliation Soundness & Contract Amendment)

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

Five tranches are complete: **P0** (lab substrate), **P0.1** (substrate remediation), **P1** (ground-truth oracle,
results-row and ledger-integrity contracts, two-phase run harness), **P1.1** (provenance + lab-state remediation),
and **P2** (capture collectors and the per-incident evidence ledger). All prior gates are green:
`bin/lab-verify` 18/18, `bin/lab-verify-p1` 24/24, `bin/lab-verify-p1.1` 16/16, `bin/lab-verify-p2` 18/18.

**P2.1 (this tranche) is a remediation.** The P2 acceptance review found one soundness defect the P2 gate did not
catch, and the governance hole that produced it:

1. `bin/lab-ledger-account` (P2 task C008) silently deviated from the frozen contract `capture-completeness.md` §4.
   The contract's mapping key is `(xid, table, action, natural_key)`; because wal2json 2.6 did not emit `xid` on the
   parsed change records, C008 dropped `xid` and used `(table, action, natural_key)` disambiguated by greedy 1:1 in
   file order.
2. That substitute key is **sound only for unique natural keys**. Under the repeated-key concurrency every real
   scenario uses, greedy 1:1 by file order can mask a co-occurring gap-and-duplicate on a shared key: counts balance
   while the ledger is corrupt. `xid` was the disambiguator that made that impossible.
3. A frozen contract was changed without a formal amendment, and the gate did not detect the deviation.

## Context you must load before doing anything

Read these, in this order, from `/home/mlasota/thesis`:

1. `sdd/.specify/memory/constitution.md` — the articles in force. Before Y001 there are fourteen; Y001 adds a
   fifteenth. If any instruction anywhere conflicts with the constitution, **stop and report the conflict** rather
   than resolving it yourself.
2. `sdd/specs/P2-capture-collectors/contracts/capture-completeness.md` — **FROZEN**. Defines the ledger and the §4
   mapping key. You may read it. You may **not** mutate it: its recorded hash in `logs/review/C001/` must keep
   verifying. It is amended by a superseding document, not by editing.
3. `sdd/specs/P2.1-reconciliation-soundness/contracts/capture-completeness.amendment-1.md` — the superseding
   amendment shipped with this tranche, frozen by Y002.
4. `sdd/specs/P1-ground-truth-harness/contracts/` and `sdd/specs/P0-lab-substrate/contracts/` — FROZEN. Unchanged.
5. `docs/P2-architecture-handoff.md` and the C008 review bundle `logs/review/C008/` — the deviation as shipped and its
   observations note. Read the mapping-key discussion carefully.
6. `sdd/specs/P2.1-reconciliation-soundness/spec.md` — what this tranche must achieve, and its acceptance criteria.
7. `sdd/specs/P2.1-reconciliation-soundness/plan.md` — decisions already locked. Do not re-litigate.
8. `sdd/specs/P2.1-reconciliation-soundness/tasks.md` — the ordered task list.
9. `sdd/specs/P2.1-reconciliation-soundness/work-instructions/WI-<TASK_TO_EXECUTE>.md` — **your actual instructions.**

`TASK_TO_EXECUTE` and `MODE` are supplied at the bottom of this prompt.

## Environment

- Host `r740core`, Ubuntu 26.04 LTS, KVM, ext4 root. You have `sudo` here.
- Victim guest `thesisvm01`, reachable by keyless SSH from the host. You have `sudo` inside the guest.
- PostgreSQL **18.4**, wal2json **2.6-3**, ZFS **2.4.1-1ubuntu5**. Devices `/dev/vdb` and `/dev/vdc` are guest-side.
- Deploy root `/home/mlasota/thesis`. Everything you create lives under it. **Never write elsewhere on the host.**
- Config is one flat file, `/home/mlasota/thesis/etc/lab.env`, sourced by everything. Discover values; never guess.
- The harness deploy root is a git repository. `bin/lab-evaluate-arm` refuses to produce a results row from a dirty
  tree (Article XIV) — so **commit your harness changes before any command that assembles a results row**. A dirty
  tree refusing a row is correct behaviour, not a bug to patch.

## Operational warnings carried forward — read before you touch anything

1. **Stop PostgreSQL before `bin/lab-reset`.** A live cluster causes exit 2 and no rollback. `lab-reset` restarts the
   cluster itself after the rollback.
2. **One slot, one consumer, database `labdb`.** Never recreate the slot in `postgres`, and never create a fresh slot
   to "fix" an invalidated one — roll back to a T1/T2 snapshot that still contains the slot instead.
3. After a T1/T2 reset the slot rewinds with `PGDATA`; the host ledger does not. Wait for `bin/lab-slot --check` to
   exit 0 (use `bin/lab-barrier`) before capturing.
4. **`bin/lab-ready` exit 0 is the entry gate** (ADR-P1.1-4). Confirm it before any capture.
5. Guest `/tmp` is mounted `noexec`. Do not remount it. Work around it.
6. `bin/lab-verify*` do not export sourced keys: invoke as `set -a; source etc/lab.env; set +a; bin/lab-verify...`.
7. **Provenance is for scoring, never for detection (Article II).** No mapping, ranking or representation path may
   read `principal`. This tranche strengthens that boundary in the reconciliation; do not weaken it.
8. **Do not add a test hatch to any boundary component (Article XII). Do not judge an acceptance criterion by
   searching prose (Article XIII). Do not silently deviate from a frozen contract (Article XV, added by Y001).**
9. Prior contracts are hash-frozen in `logs/review/`. Keep them that way — including `capture-completeness.md`.

## Rules of engagement

1. **Scope.** Do only the task named in `TASK_TO_EXECUTE`. Do not start the next task, do not "while I'm here" fix
   things, do not refactor files owned by another task. Record any out-of-scope defect in
   `logs/review/<task-id>/observations.md` and continue.
2. **Dependencies.** Verify the `Depends on` tasks in your WI are complete (their review bundles exist and their
   assertions passed). If not, stop and report.
3. **Idempotence.** Every script must be safe to re-run. Re-running a completed task must not destroy state or
   duplicate data; it detects existing correct state and reports `"changed": false`.
4. **No invention.** If a value is unknown, discover it and record it in `etc/lab.env`. Never hardcode a guess.
5. **Determinism in the measured path (Article I).** No language model participates anywhere in P2.1.
6. **Provenance is for scoring, never for detection (Article II).** The mapping key must be computable without
   reading `principal`.
7. **Stock mechanisms only (Article V).** No WAL parser, no `pg_waldump` builds, no filesystem event daemon, no
   `zfs send`/clones/loop mounts, no bespoke server, broker or queue, no ORM or web framework.
8. **Fail loud (Article VIII).** No `|| true` on a check. Every integrity test includes a deliberate-regression case
   proving the check detects a violation, then passes again after the fault is reverted.
9. **Simplicity (Article VI).** POSIX shell, SQL, Python 3 only. Prefer a short script in `bin/` over a package.
10. **Do not mutate a frozen contract.** `capture-completeness.md` stays byte-identical. Amend by superseding
    document only (Article XV).
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
5. `sdd/specs/P2.1-reconciliation-soundness/checklist.md` has your task's row updated with the date and bundle path.
   You do **not** fill in the `Reviewed` column; the operator owns that.

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

Expect a sceptical human who has already caught this project shipping a self-attested green build three times, and
caught this exact tranche's defect by reading the reconciliation source rather than the handoff. They will read your
`RESULT` line, then `acceptance.md` checking the tier column, then the negative-test evidence, then `observations.md`,
then spot-check two artefacts by hand. For Y002 they will hand-trace one repeated-key incident through the mapping.
Write those files for a reader who assumes the happy path was not actually tested and that any claim not mechanically
re-derived is unproven.

---
