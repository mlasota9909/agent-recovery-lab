# Agent prompt — SDD, Tranche P3 (Derived Analytics & the Arm A Deterministic Ranker)

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

**This tranche, P3, builds Arm A and the analytics beneath it.** Everything upstream built and certified the evidence
ledger. P3 is the first layer of intelligence over it: deterministic detection (per-window change-burst density,
churn, deletion spikes, DDL flags, mean+3σ anomaly scoring), candidate recovery-coordinate generation, the
deterministic ranking function, and the naive comparator. Arm A is the reproducible number the whole experiment is
measured against, and Arm B (P6) will be judged by whether the representation lets a modest model match or beat it.

## Where the build stands

Six tranches are complete: **P0** (lab substrate), **P0.1** (substrate remediation), **P1** (the instruments:
ground-truth oracle, results-row and ledger-integrity contracts, two-phase run harness, stubs), **P1.1** (provenance
and lab-state remediation), **P2** (capture collectors and the append-only ledger), and **P2.1** (reconciliation
soundness + the frozen-contract amendment that restored the `(xid, table, action, natural_key)` mapping key). Gates
in force, all exit 0:

- `bin/lab-verify` — **TIER M 9/9 · TIER A 9/9 · TOTAL 18/18**
- `bin/lab-verify-p1` — **TIER M 23/23 · TIER A 1/1 · TOTAL 24/24**
- `bin/lab-verify-p1.1` — **TIER M 15/15 · TIER A 1/1 · TOTAL 16/16**
- `bin/lab-verify-p2` — **TIER M 17/17 · TIER A 1/1 · TOTAL 18/18**
- `bin/lab-verify-p2.1` — **TIER M 15/15 · TIER A 1/1 · TOTAL 16/16**

These exist and must be **reused, not rebuilt**: `bin/lab-query` (the no-ETL DuckDB view layer over the ledger, with
default views that already exclude the `principal` provenance field), `bin/lab-ledger-account` (exactly-once
reconciliation — the entry gate for analytics), `bin/lab-coordinate` (heartbeat→LSN→snapshot resolution),
`bin/lab-generate-incident` and the two-phase `generate-incident`/`evaluate-arm` harness (P1), the ground-truth
oracle (P1), `bin/lab-capture` and `bin/lab-capture-workload` (P2), `bin/lab-ready`, `bin/lab-slot`, `bin/lab-barrier`,
`bin/lab-reset`. Read what exists before writing anything; wire and complete, do not reinvent.

## The two entry conditions for P3 — check both before any task

1. **`bin/lab-ready` must exit 0, and the incident under analysis must have passed `bin/lab-ledger-account`**
   (ADR-P2-7). P3 may not run detection over an unreconciled ledger. If either fails, **stop and report** — do not
   work around it.
2. **The working tree must be clean before producing any artefact that carries provenance or a results row**
   (Article XIV). Commit harness changes before you run anything that records `harness_commit`. A refusal on a dirty
   tree is correct behaviour, not a defect to patch.

## Context you must load before doing anything

Read these, in this order, from `<repo>`:

1. `sdd/.specify/memory/constitution.md` — the articles in force. There are **fifteen** (I determinism, II provenance
   for scoring not detection, V stock mechanisms, VI simplicity, VIII fail loud, X lab containment, XII no test
   hatches in boundaries, XIII verification tiers, XIV provenance of record, XV amend-by-supersession, among others).
   If any instruction anywhere conflicts with the constitution, **stop and report the conflict** rather than resolving
   it yourself.
2. `sdd/specs/P1-ground-truth-harness/contracts/results-row.md` — FROZEN. The `recovery_coordinate` fields Arm A and
   the naive comparator populate, and the recovery-point-error fields the oracle computes.
3. `sdd/specs/P1-ground-truth-harness/contracts/ledger-integrity.md` — FROZEN. The invariants the ledger you read obeys.
4. `sdd/specs/P2-capture-collectors/contracts/capture-completeness.md` **and**
   `sdd/specs/P2.1-reconciliation-soundness/contracts/capture-completeness.amendment-1.md` — FROZEN. The ledger shape
   and the exactly-once mapping key. §5 of the completeness contract states the provenance rule you must obey.
5. `sdd/specs/P3-analytics-ranker/contracts/candidate-coordinate.md` and `.../contracts/arm-coordinate.md` — FROZEN by
   D001. The record schemas your analytics and ranker emit.
6. `docs/P2-architecture-handoff.md` (and the P1/P1.1 handoffs) — current topology and operational warnings.
7. `sdd/specs/P3-analytics-ranker/spec.md`, then `plan.md`, then `tasks.md`.
8. `sdd/specs/P3-analytics-ranker/work-instructions/WI-<TASK_TO_EXECUTE>.md` — **your actual instructions.**

`TASK_TO_EXECUTE` and `MODE` are supplied at the bottom of this prompt.

## Environment

- Host `r740core`, Ubuntu 26.04 LTS, KVM, ext4 root. You have `sudo` here.
- Victim guest `thesisvm01`, reachable by keyless SSH from the host. You have `sudo` inside the guest.
- PostgreSQL **18.4**, wal2json **2.6-3**, ZFS **2.4.1-1ubuntu5**. Devices `/dev/vdb` and `/dev/vdc` are guest-side.
- DuckDB is the sanctioned analytical query tool and P3 adds **no** new third-party runtime. All analytics are
  DuckDB SQL, Python 3 and POSIX shell.
- Deploy root `<repo>`. Everything you create lives under it. **Never write elsewhere on the host.**
- Config is one flat file, `<repo>/etc/lab.env`, sourced by everything. Discover values; never guess.
- The harness deploy root is a git repository. Its HEAD is the harness version recorded in `harness_commit`.

## Operational warnings carried forward — read before you touch anything

1. **Stop PostgreSQL before `bin/lab-reset`.** A live cluster causes exit 2 and no rollback. `lab-reset` restarts it.
2. **One slot, one consumer, database `labdb`.** Never recreate the slot in the `postgres` database, and never create
   a fresh slot to "fix" an invalidated one — roll back to a T1/T2 snapshot that still contains it.
3. After a T1/T2 reset the slot rewinds with `PGDATA`; the host ledger does not. Wait for `bin/lab-slot --check`
   exit 0 (use `bin/lab-barrier`) before capturing.
4. Guest `/tmp` is mounted `noexec`. Do not remount it. Work around it.
5. `bin/lab-verify*` do not export sourced keys: invoke as `set -a; source etc/lab.env; set +a; bin/lab-verify`.
6. `bin/lab-consumer status` and `bin/lab-slot --check` need the open incident id; discover it from `archive/current`.
7. **All LSN comparison is integer `(high<<32)+low`, never string.** The `3/9` vs `3/10` ordering trap is real and
   has bitten this project; a required test case covers it.
8. Prior contracts are hash-frozen in `logs/review/`. Keep them byte-identical.

## Rules of engagement

1. **Scope.** Do only the task named in `TASK_TO_EXECUTE`. Do not start the next task, do not "while I'm here" fix
   things, do not refactor files owned by another task. Record any out-of-scope defect in
   `logs/review/<task-id>/observations.md` and continue.
2. **Dependencies.** Verify the `Depends on` tasks in your WI are complete (their review bundles exist and their
   assertions passed). If not, stop and report.
3. **Idempotence.** Every script is safe to re-run: it detects existing correct state and reports `"changed": false`,
   never duplicating data or corrupting the ledger.
4. **No invention.** If a value is unknown, discover it and record it in `etc/lab.env`. Never hardcode a guess.
5. **Determinism everywhere (Article I).** No language model participates anywhere in P3. Every analytic and the
   ranker are deterministic and reproducible: same ledger → byte-identical output, asserted by re-run.
6. **Provenance is for scoring, never for detection (Article II).** Analytics (C5) and the ranker (C7) read only the
   provenance-blind default views. The `principal`/`session_user`/`usename`/UID fields are invisible to detection.
   Only the P1 oracle's scoring path may read them. This is enforced by a mechanical negative test in D009.
7. **Detection does not peek at the answer.** The ranker's inputs are the provenance-blind ledger view and an
   operator-supplied *approximate* incident time — never the injection log, never the oracle's known optimum.
8. **Stock mechanisms only (Article V).** DuckDB SQL over the ledger; no bespoke store, no ORM, no web framework, no
   ML library, no model call. If you find yourself adding one, stop and report.
9. **Fail loud (Article VIII).** No `|| true` on a check. Every integrity/΅comparison test includes a deliberate
   regression case proving the check detects a violation, then passes again after revert.
10. **Simplicity (Article VI).** POSIX shell, SQL, Python 3, DuckDB SQL only. Prefer a short script in `bin/` over a
    package.
11. **The naive comparator is mandatory and must never be rigged.** Its injected incident-time error is read from the
    scenario config — a declared, fixed parameter — not computed to make Arm A look good.
12. **Lab containment (Article X).** All data synthetic. No production data, no personal data, no outbound calls.

## MODE semantics

- `MODE: DRY_RUN` — change nothing. Produce `logs/review/<task-id>/dry-run.md` with: the exact commands you intend to
  run in order, the files you intend to create or edit with a one-line purpose each, the preconditions you checked and
  their observed values (including `bin/lab-ready` exit status and the reconciliation status of the target incident),
  and any ambiguity to resolve before executing. Then stop.
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
5. `sdd/specs/P3-analytics-ranker/checklist.md` has your task's row updated with the date and bundle path. You do
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

Expect a sceptical human who has already caught this project shipping a self-attested green build four times. They
will read your `RESULT` line, then `acceptance.md` checking the tier column, then the negative-test evidence, then
`observations.md`, then spot-check two artefacts by hand. For P3 they will pay closest attention to two things: the
**provenance-blindness** negative test (they will confirm that stripping the principal field genuinely leaves the
chosen coordinate byte-identical, not that a comment claims it does), and the **headline SC-01 result** (they will
read both Arm A and naive recovery-point errors straight from the results row and confirm Arm A won honestly, with a
declared, fixed naive-error parameter). Write your bundle for a reader who assumes the happy path was not actually
tested and that any claim not mechanically re-derived is unproven.

---
