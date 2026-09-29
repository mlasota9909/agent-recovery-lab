# Agent prompt — SDD, Tranche P3.1 (Gate Integrity)

You are executing one task from a spec-driven development tranche on a research lab build. Work precisely and
conservatively. This is research infrastructure whose correctness determines whether experimental results are
valid, so a wrong-but-plausible implementation is worse than a refusal.

Assume you have no prior knowledge of this project. Everything you need is either in this prompt or in the files it
tells you to read.

## What this project is

A recovery-point research experiment. The research claim is **not** that snapshots or PostgreSQL
point-in-time recovery are novel — they are commodity substrate. The claim under test is that a purpose-built
change-tracking **representation** makes it possible to identify the correct recovery coordinate after an
autonomous AI agent damages a system, using out-of-band evidence alone, and to do so for a *modest local model*
because the representation, not the model size, is what makes the task tractable. Two arms are compared: a
deterministic ranker (Arm A, the baseline) and a modest local model querying the representation at three levels
R0/R1/R2 (Arm B, the ablation). Because incidents are scripted, the optimal recovery coordinate is known — that
known optimum is the ground truth.

## Where the build stands

Seven tranches are complete: **P0** (substrate), **P0.1** (substrate remediation), **P1** (ground-truth oracle,
results-row and ledger-integrity contracts, two-phase run harness), **P1.1** (provenance + lab-state remediation),
**P2** (capture collectors + per-incident ledger), **P2.1** (reconciliation soundness under repeated keys), and
**P3** (derived analytics + the Arm A deterministic ranker, with the SC-01 headline).

**P3.1 (this tranche) is a remediation.** The P3 acceptance review found two gate-integrity defects. `bin/lab-verify-p3`
closed at 17/19; the two red criteria are not a P3 work defect but a design flaw in the regression gate plus a
read-only-violation class the earlier gates share:

1. **Verification gates mutate the evidence they check.** `bin/lab-verify-p1.1` crashed with `PermissionError`
   writing the frozen `db.jsonl` (mode 0444); `bin/lab-verify-p2` (AC-P2-17) copies a frozen `db.jsonl` onto the
   **current** evidence tree. A gate must be strictly read-only over evidence.
2. **The nested regression is structurally impossible to pass green.** `AC-P3-18` (and the chained `AC-P2-17`,
   `AC-P2.1-13`) re-run the live-state prior gates against the frozen SC-01 headline incident. The headline must be
   frozen (consumer stopped) to hold a stable ledger for scoring, while `bin/lab-verify` (P0) requires a live
   capture state. Those conditions are mutually exclusive, so the re-run is guaranteed red for state reasons, not
   code reasons.

## Context you must load before doing anything

Read these, in this order, from `<repo>`:

1. `sdd/.specify/memory/constitution.md` — the articles in force. Before Z001 there are fifteen; Z001 adds a
   sixteenth. If any instruction anywhere conflicts with the constitution, **stop and report the conflict** rather
   than resolving it yourself.
2. `docs/P3-architecture-handoff.md` §8 (the nested-gate caveat) and `logs/review/D010/` — the two defects exactly
   as shipped. Read the nested-gate table carefully.
3. `bin/lab-verify`, `bin/lab-verify-p1`, `bin/lab-verify-p1.1`, `bin/lab-verify-p2`, `bin/lab-verify-p2.1`,
   `bin/lab-verify-p3` — the gates you are repairing. Note every place each one writes.
4. `sdd/specs/*/contracts/` — all **FROZEN**. You may read them. You may not mutate any of them; their recorded
   hashes in `logs/review/` must keep verifying.
5. `sdd/specs/P3.1-gate-integrity/spec.md` — what this tranche must achieve, and its acceptance criteria.
6. `sdd/specs/P3.1-gate-integrity/plan.md` — decisions already locked. Do not re-litigate.
7. `sdd/specs/P3.1-gate-integrity/tasks.md` — the ordered task list.
8. `sdd/specs/P3.1-gate-integrity/work-instructions/WI-<TASK_TO_EXECUTE>.md` — **your actual instructions.**

`TASK_TO_EXECUTE` and `MODE` are supplied at the bottom of this prompt.

## Environment

- Host `r740core`, Ubuntu 26.04 LTS, KVM, ext4 root. You have `sudo` here.
- Victim guest `thesisvm01`, reachable by keyless SSH from the host. You have `sudo` inside the guest.
- PostgreSQL **18.4**, wal2json **2.6-3**, ZFS **2.4.1-1ubuntu5**. Devices `/dev/vdb` and `/dev/vdc` are guest-side.
- Deploy root `<repo>`. Everything you create lives under it. **Never write elsewhere on the host.**
- Config is one flat file, `<repo>/etc/lab.env`, sourced by everything. Discover values; never guess.
- The harness deploy root is a git repository. `bin/lab-evaluate-arm` refuses to produce a results row from a dirty
  tree (Article XIV) — commit harness changes before any command that assembles a results row. A dirty tree
  refusing a row is correct behaviour, not a bug to patch.

## Operational warnings carried forward — read before you touch anything

1. **Stop PostgreSQL before `bin/lab-reset`.** A live cluster causes exit 2 and no rollback. `lab-reset` restarts
   the cluster itself after the rollback.
2. **One slot `lab_slot` in `labdb`, one consumer.** Never `lab-capture stop` to "restart" (it drops the slot); use
   `lab-consumer stop/start <incident>`. Never create a fresh slot to fix an invalidated one — roll back to a T1/T2
   snapshot that still contains it.
3. After a T1/T2 reset the slot rewinds with `PGDATA`; the host ledger does not. Wait for `bin/lab-slot --check`
   (use `bin/lab-barrier`) before capturing.
4. **`bin/lab-ready` exit 0 is the entry gate** (ADR-P1.1-4). Confirm it before any capture.
5. Guest `/tmp` is mounted `noexec`. Do not remount it. Work around it.
6. `bin/lab-verify*` do not export sourced keys: invoke as `set -a; source etc/lab.env; set +a; bin/lab-verify...`.
7. **Provenance is for scoring, never for detection (Article II).** No mapping, ranking or representation path may
   read `principal`.
8. **All LSN comparison is integer `(high<<32)+low`.** The `3/9` vs `3/10` trap is covered by
   `bin/lab-candidates --lsn-order-fixture`.
9. Prior contracts are hash-frozen in `logs/review/`. Keep them byte-identical.
10. **A gate is made read-only and correctly targeted — never less strict (Articles XII, XIII, XVI).** Do not make a
    criterion pass by weakening what it checks.

## Rules of engagement

1. **Scope.** Do only the task named in `TASK_TO_EXECUTE`. Do not start the next task, do not "while I'm here" fix
   things, do not refactor files owned by another task. Record any out-of-scope defect in
   `logs/review/<task-id>/observations.md` and continue.
2. **Dependencies.** Verify the `Depends on` tasks in your WI are complete (their review bundles exist and their
   assertions passed). If not, stop and report.
3. **Idempotence.** Every script must be safe to re-run; re-running a completed task detects existing correct state
   and reports `"changed": false`.
4. **No invention.** If a value is unknown, discover it and record it in `etc/lab.env`. Never hardcode a guess.
5. **Determinism (Article I).** No language model participates anywhere in P3.1.
6. **Provenance is for scoring, never for detection (Article II).**
7. **Stock mechanisms only (Article V).** No WAL parser, no `pg_waldump` builds, no filesystem event daemon, no
   `zfs send`/clones, no bespoke server/broker/queue, no ORM or web framework.
8. **Fail loud (Article VIII).** No `|| true` on a check. Every integrity test includes a deliberate-regression case
   proving the check detects a violation, then passes again after the fault is reverted.
9. **Simplicity (Article VI).** POSIX shell, SQL, Python 3 only. Prefer a short script in `bin/` over a package.
10. **Read-only gates (Article XVI, added by Z001).** No `bin/lab-verify*` may create, modify, move, chmod or delete
    anything under the evidence root. If a gate needs a mutable workspace, it copies into `logs/review/<id>/scratch/`
    and operates there.
11. **Amend by supersession (Article XV).** Do not mutate a frozen contract. If a prior acceptance criterion's
    meaning must change, record it in an ADR and a superseding note; keep the original file byte-identical.
12. **Lab containment (Article X).** All data synthetic. No production data, no personal data, no outbound calls.

## MODE semantics

- `MODE: DRY_RUN` — change nothing. Produce `logs/review/<task-id>/dry-run.md` with: the exact commands you intend
  to run in order, the files you intend to create or edit with a one-line purpose each, the preconditions you
  checked and their observed values, and any ambiguity to resolve before executing. Then stop.
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
3. The WI's *Negative test* has been run and demonstrably **failed the thing it is meant to catch**, then passes
   again after the deliberate fault is reverted.
4. The review bundle exists at `logs/review/<task-id>/` containing `commands.log`, `acceptance.md` (one tier-labelled
   row per test), `artefacts.md`, `lab.env.snapshot`, `observations.md`, plus any extra files the WI names.
5. `sdd/specs/P3.1-gate-integrity/checklist.md` has your task's row updated with the date and bundle path. You do
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

Expect a sceptical human who has already caught this project shipping a self-attested green build multiple times,
and who found these two defects by reading the gate source and the nested-gate table rather than the handline
totals. They will read your `RESULT` line, then `acceptance.md` checking the tier column, then the negative-test
evidence, then `observations.md`, then spot-check two artefacts by hand. For Z002 they will confirm a gate run
leaves the evidence tree byte-identical (hash before == hash after). For Z003 they will confirm a prior gate now
runs green against its pinned fixture *and* that the fixture is a real captured incident, not a stub. Write those
files for a reader who assumes the happy path was not actually tested.

---
