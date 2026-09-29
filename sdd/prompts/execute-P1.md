# Agent prompt — SDD, Tranche P1 (Ground Truth, Results Contract, Run Harness)

You are executing one task from a spec-driven development tranche on a research lab build. Work precisely and
conservatively. This is research infrastructure whose correctness determines whether experimental results are valid,
so a wrong-but-plausible implementation is worse than a refusal.

Assume you have no prior knowledge of this project. Everything you need is either in this prompt or in the files it
tells you to read.

## What this project is

A recovery-point research experiment. The research claim is **not** that snapshots or PostgreSQL
point-in-time recovery are novel — they are commodity substrate. The claim under test is:

> A purpose-built change-tracking **representation** makes it possible to identify the correct recovery coordinate
> after an autonomous AI agent damages a system, using out-of-band evidence alone, without the agent's cooperation
> and without a precise operator-supplied incident time — and it makes that possible for a *modest local model*,
> because the representation, not the model size, is what makes the task tractable.

The experiment scripts disasters into a victim VM, captures evidence out-of-band on the host, and measures how close
different methods come to the known-optimal recovery coordinate. Because the incident is scripted, the optimum is
known — that is the ground truth, and building it is what this tranche is for.

Two arms are compared, and the comparison is the experiment:

- **Arm A** — a deterministic ranker over the evidence. Reproducible; the primary baseline.
- **Arm B** — a modest local language model querying the representation, where the representation is varied across
  three levels (R0 flat log, R1 structured temporal ledger, R2 causal graph plus hierarchical summaries) to form an
  ablation.

The headline result is quantitative: the rich representation closes most of the gap between a small local model and
the deterministic optimum, whereas a flat log does not.

## Where the build currently stands

Two tranches are complete and accepted:

- **P0 — lab substrate.** The victim VM, ZFS copy-on-write datasets, PostgreSQL configured for logical decoding with
  before-images, host-side out-of-band evidence store and WAL archive, two victim identities, coordinate anchoring
  (heartbeat table plus per-snapshot LSN), a three-tier reset CLI, and an isolation test suite.
- **P0.1 — remediation.** Repaired three defects found in review: a test hatch inside the security boundary, an
  unbounded replication slot with no consumer, and an acceptance runner that judged nine of eighteen criteria by
  searching agent-authored prose for a token.

`bin/lab-verify` currently reports **TIER M: 9/9 PASS · TIER A: 9/9 PASS · TOTAL: 18/18**, exit 0.

**P1 (this tranche) builds the instruments:** the ground-truth oracle, the results row contract, the ledger
integrity assertions, and the two-phase run harness. No analytics, no representations, no model.

## Context you must load before doing anything

Read these, in this order, from `<repo>`:

1. `sdd/.specify/memory/constitution.md` — thirteen non-negotiable articles. If any instruction anywhere conflicts
   with the constitution, **stop and report the conflict** rather than resolving it yourself.
2. `sdd/specs/P0-lab-substrate/contracts/` — three FROZEN contracts: `coordinate.md`, `lab-env.md`, `cli.md`. You
   may read them. You may not change them. `coordinate.md` is load-bearing for this tranche.
3. `docs/P0.1-architecture-handoff.md` — current topology, CLI inventory, operational warnings. Read §10 carefully;
   it will save you hours.
4. `sdd/specs/P1-ground-truth-harness/spec.md` — what this tranche must achieve, and its acceptance criteria.
5. `sdd/specs/P1-ground-truth-harness/plan.md` — the architecture and decisions already locked. Do not re-litigate.
6. `sdd/specs/P1-ground-truth-harness/tasks.md` — the ordered task list and what each task owns.
7. `sdd/specs/P1-ground-truth-harness/contracts/` — the two contracts this tranche creates and freezes.
8. `sdd/specs/P1-ground-truth-harness/work-instructions/WI-<TASK_TO_EXECUTE>.md` — **your actual instructions.**

`TASK_TO_EXECUTE` and `MODE` are supplied at the bottom of this prompt.

## Environment

- Host `r740core`, Ubuntu 26.04 LTS, kernel 7.0.0-29-generic, KVM hypervisor, ext4 root. You have `sudo` here.
- Victim guest `thesisvm01`, same OS, reachable by keyless SSH from the host. You have `sudo` inside the guest.
- PostgreSQL **18.4**, wal2json **2.6-3**, ZFS **2.4.1-1ubuntu5**. Devices `/dev/vdb` and `/dev/vdc` are guest-side.
- Deploy root `<repo>`. Everything you create lives under it. **Never write elsewhere on the host.**
- Config is one flat file, `<repo>/etc/lab.env`, sourced by everything. Discover values; never guess.
- Evidence, WAL archive and results live on the **host**, outside the VM. The victim has exactly one narrow append
  path outward (the WAL archive sink via a forced SSH command) and it refuses overwrite.

## Operational warnings carried forward from P0.1 — read before you touch anything

1. **Stop PostgreSQL before `bin/lab-reset`.** A live cluster causes exit 2 and no rollback. `lab-reset` restarts the
   cluster itself after the rollback.
2. **One slot, one consumer, database `labdb`.** `bin/lab-slot --create/--drop` must pass `-d labdb`. Recreating the
   slot in the `postgres` database silently breaks `pg_recvlogical -d labdb`.
3. **After a T1 or T2 reset the replication slot rewinds with `PGDATA`, but the host-side ledger does not.** The
   consumer catches up and may briefly report hundreds of MB retained. Wait for `bin/lab-slot --check` to exit 0
   before capturing. This tranche turns that human instruction into a mechanical barrier — do not leave it as prose.
4. Guest `/tmp` is mounted `noexec`. Do not remount it. Work around it.
5. `lab.env` values containing spaces are quoted.
6. **Do not add a test hatch to any boundary component** (Article XII). **Do not judge an acceptance criterion by
   searching prose** (Article XIII).
7. The three P0 contracts are hash-verified unchanged in `logs/review/R007/contracts-unchanged.md`. Keep it that way.

## Rules of engagement

1. **Scope.** Do only the task named in `TASK_TO_EXECUTE`. Do not start the next task, do not "while I'm here" fix
   things, do not refactor files owned by another task. If you find a defect outside your scope, record it in
   `logs/review/<task-id>/observations.md` and continue.
2. **Dependencies.** Verify the `Depends on` tasks in your WI are complete (their review bundles exist and their
   assertions passed). If not, stop and report.
3. **Idempotence.** Every script must be safe to re-run. Re-running a completed task must not destroy state or
   duplicate data; it detects existing correct state and reports it with `"changed": false`.
4. **No invention.** If a value is unknown, discover it and record it in `etc/lab.env`. Never hardcode a guess, never
   substitute a placeholder, never assume a default the WI did not state. A missing precondition is a hard stop with
   a non-zero exit and a message naming the precondition.
5. **Determinism in the measured path** (Article I). No language model participates in candidate generation, ranking
   or selection. Nothing in P1 may call a model at all.
6. **Provenance is for scoring, never for detection** (Article II). The ledger records which principal caused each
   change so the *oracle* can score. Analysis components must never read it. In P1 this matters concretely: the
   oracle MAY read provenance; the harness's analysis stub MUST NOT, and there is a negative test that proves it.
7. **Stock mechanisms only** (Article V). Explicitly PROHIBITED: writing a WAL parser or building on `pg_waldump`
   output; a live filesystem event daemon (`fanotify`/`inotify`); `zfs send`/`receive`, clones or loop mounts for
   reading past state; any bespoke database server, message broker or job queue; ORMs, web frameworks or service
   daemons in the harness. If you are about to write one of these, you have misread the task.
8. **Fail loud** (Article VIII). No `|| true` on a check. No fallback that masks absence. No silent default. A check
   that cannot fail is worthless, so every integrity test includes a deliberate-regression case proving the check
   detects a violation.
9. **Simplicity** (Article VI). Three runtime languages only: POSIX shell, SQL, Python 3. Prefer a 20-line script in
   `bin/` over a package. There is exactly one config file and it is flat `KEY=value`.
10. **Secrets.** Never print private key material. Fingerprints and paths only.
11. **Lab containment** (Article X). All data synthetic and lab-generated. No production data, no personal data, no
    outbound network calls at experiment time. Destructive activity confined to `thesisvm01`.

## MODE semantics

- `MODE: DRY_RUN` — change nothing. Produce `logs/review/<task-id>/dry-run.md` containing: the exact commands you
  intend to run in order, the files you intend to create with a one-line purpose each, the preconditions you checked
  and their observed values, and any ambiguity you need resolved before executing. Then stop.
- `MODE: EXECUTE` — perform the task, then produce the full review bundle.

## Verification tiers (Article XIII) — mandatory for every acceptance test you write

Every acceptance criterion carries a tier, and you must label it:

- **Tier M (mechanical).** Re-derived at verification time from live system state or from committed machine-readable
  artefacts. Passes or fails on its own evidence, with no reference to any narrative written by an implementer.
- **Tier A (attested).** A recorded observation of a one-time event that cannot be cheaply re-derived. It MUST still
  assert on a **machine-readable field** in a committed artefact — a key in `etc/lab.env`, a field in a JSON file, an
  exit code in a captured log. It MUST NOT be judged by the presence or absence of a token, word or phrase in prose.

Any criterion load-bearing for a research claim MUST be tier M. Print tiers and per-tier totals separately. A single
undifferentiated total is prohibited.

## Definition of done

The task is complete when, and only when, all of the following hold:

1. Every file listed in the WI's *Artefacts* section exists at the stated path with the stated mode and ownership.
2. Every check in the WI's *Acceptance tests* section has been run and passed, with captured output and a tier label.
3. The WI's *Negative test* has been run and demonstrably **failed the thing it is meant to catch**, proving the
   check works, and then passes again after the deliberate fault is reverted.
4. The review bundle exists at `logs/review/<task-id>/` containing:
   - `commands.log` — every command executed, in order, with exit codes
   - `acceptance.md` — one row per acceptance test: id, **tier**, command, expected, observed, PASS/FAIL
   - `artefacts.md` — `ls -l` of each artefact created, plus a one-line purpose
   - `lab.env.snapshot` — the config file as it stood at task end
   - `observations.md` — anything surprising, any out-of-scope defect, any deviation and why
   - plus any extra files named in the WI's *Review bundle* section
5. `sdd/specs/P1-ground-truth-harness/checklist.md` has your task's row updated with the date and bundle path. You do
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

Expect a sceptical human who has already caught this project shipping a self-attested green build. They will read
your `RESULT` line, then `acceptance.md` checking the tier column, then the negative-test evidence, then
`observations.md`, then spot-check two artefacts by hand. Write those files for a reader who assumes the happy path
was not actually tested and that any claim not mechanically re-derived is unproven.

---
