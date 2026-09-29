# Agent prompt — SDD, Tranche P4 (Restore, Validation & the Promotion Gate)

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

**This tranche, P4, closes the loop.** Upstream tranches built the evidence ledger (P2/P2.1) and the deterministic
detection-and-ranking layer that turns it into a recovery coordinate (P3). P4 performs the *real* recovery from a
coordinate — PITR of PostgreSQL into an isolated sandbox, a ZFS clone of the filesystem subtree, and validation of the
restored state against the ground-truth oracle manifest at row, byte and schema level — ending in a consistency verdict
and a promotion gate. Its defining test: **feed the known ground-truth coordinate and the restore must validate clean.**
If the perfect coordinate does not reproduce the pre-incident state exactly, the measurement apparatus is wrong.

## Where the build stands

Eight tranches are complete: **P0** (lab substrate), **P0.1** (substrate remediation), **P1** (ground-truth oracle,
results-row and ledger-integrity contracts, two-phase run harness), **P1.1** (provenance and lab-state remediation),
**P2** (capture collectors and the append-only ledger), **P2.1** (reconciliation soundness + the amendment that
restored the `(xid, table, action, natural_key)` mapping key), **P3** (derived analytics + the Arm A deterministic
ranker + naive comparator + SC-01 realized as a reconciled incident), and **P3.1** (gate integrity: read-only
verification gates and the redesigned per-fixture regression harness). Gates in force, all exit 0:

- `bin/lab-verify` — **TIER M 9/9 · TIER A 9/9 · TOTAL 18/18**
- `bin/lab-verify-p1` — **TIER M 23/23 · TIER A 1/1 · TOTAL 24/24**
- `bin/lab-verify-p1.1` — **TIER M 15/15 · TIER A 1/1 · TOTAL 16/16**
- `bin/lab-verify-p2` — **TIER M 17/17 · TIER A 1/1 · TOTAL 18/18**
- `bin/lab-verify-p2.1` — **TIER M 15/15 · TIER A 1/1 · TOTAL 16/16**
- `bin/lab-verify-p3` — **TIER M 18/18 · TIER A 1/1 · TOTAL 19/19**
- `bin/lab-verify-p3.1` — **TIER M 15/15 · TIER A 1/1 · TOTAL 16/16**

These exist and must be **reused, not rebuilt**: `bin/lab-coordinate` (heartbeat->LSN->snapshot resolution, ADR-008 —
the newest snapshot with LSN <= target); the P1 ground-truth **oracle** and its **manifest** (the known-good
pre-incident state: per-relation row counts + content hashes, per-file byte hashes, schema DDL); the P1 two-phase
`generate-incident`/`evaluate-arm` harness and FROZEN `results-row.md`; `bin/lab-inject-sc01` and the SC-01 incident
(P3); `bin/lab-rank` (Arm A) and `bin/lab-naive` producing `arm-coordinate` records (P3); `bin/lab-ledger-account`
(reconciliation entry gate); `bin/lab-ready`, `bin/lab-reset`, `bin/lab-slot`, `bin/lab-barrier`; `bin/lab-regression`
and `bin/lab-gate-readonly-check` (P3.1). Read what exists before writing anything; wire and complete, do not reinvent.

## The safety rule that defines P4 — read before any task

**Restore is read-only with respect to the victim and the evidence store.** Concretely:

- **DB restore** replays the host-side base backup + archived WAL into a **new sandbox cluster** with its own PGDATA
  and its own port. You must **never** run `pg_ctl`/`systemctl` against the victim cluster, and never point recovery at
  the victim's live PGDATA.
- **FS restore** uses **`zfs clone`** of the resolved snapshot into a sandbox mountpoint. You must **never** use
  `zfs rollback` (it destroys the victim's current state) or otherwise write the victim dataset.
- **Promotion** (replacing the "production" state with the restored state) is a separate, gated step. It requires a
  clean verdict AND an explicit operator authorization token, and in the lab it is a **logged simulation only** — it
  never overwrites the victim or the evidence store.

Enforced mechanically: a whole-of-victim-plus-evidence manifest must be byte-identical before and after a full
restore-and-validate cycle. If it changes, the restore path touched something it must not, and the task FAILs.

## The two entry conditions for P4 — check both before any task

1. **`bin/lab-ready` must exit 0, and the incident under restore must have passed `bin/lab-ledger-account`**
   exactly-once (ADR-P2-7). If either fails, **stop and report** — do not work around it.
2. **The working tree must be clean before producing any artefact that carries provenance or a results row**
   (Article XIV). A refusal on a dirty tree is correct behaviour, not a defect to patch.
3. P4 restores only against a coordinate whose `selection_inputs` no-peek check passed (arm-coordinate §4). Never
   restore against a coordinate that read the injection log or the oracle optimum.

## Context you must load before doing anything

Read these, in this order, from `<repo>`:

1. `sdd/.specify/memory/constitution.md` — the articles in force. There are **sixteen** (I determinism, II provenance
   for scoring not detection, V stock mechanisms, VI simplicity, VIII fail loud, X lab containment, XII no test hatches
   in boundaries, XIII verification tiers, XIV provenance of record, XV amend-by-supersession, XVI read-only
   verification gates, among others). If any instruction anywhere conflicts with the constitution, **stop and report
   the conflict** rather than resolving it yourself.
2. `sdd/specs/P1-ground-truth-harness/contracts/results-row.md` — FROZEN. The `recovery_coordinate` fields a
   coordinate populates and the recovery-point-error fields the oracle computes.
3. `sdd/specs/P1-ground-truth-harness/contracts/ledger-integrity.md` — FROZEN.
4. `sdd/specs/P2-capture-collectors/contracts/capture-completeness.md` **and**
   `sdd/specs/P2.1-reconciliation-soundness/contracts/capture-completeness.amendment-1.md` — FROZEN.
5. `sdd/specs/P3-analytics-ranker/contracts/arm-coordinate.md` — FROZEN. The coordinate shape P4 restores against,
   including the `selection_inputs` no-peek audit block.
6. `sdd/specs/P4-restore-validation/contracts/restore-report.md` and `.../contracts/promotion-gate.md` — FROZEN by
   E001. The verdict record your validation emits and the validate-vs-promote boundary you must obey.
7. `docs/P3-architecture-handoff.md` (and the P2/P2.1/P3.1 handoffs) — current topology and operational warnings,
   including where the base backup and WAL archive live on the host.
8. `sdd/specs/P4-restore-validation/spec.md`, then `plan.md`, then `tasks.md`.
9. `sdd/specs/P4-restore-validation/work-instructions/WI-<TASK_TO_EXECUTE>.md` — **your actual instructions.**

`TASK_TO_EXECUTE` and `MODE` are supplied at the bottom of this prompt.

## Environment

- Host `r740core`, Ubuntu 26.04 LTS, KVM, ext4 root. You have `sudo` here.
- Victim guest `thesisvm01`, reachable by keyless SSH from the host. You have `sudo` inside the guest.
- PostgreSQL **18.4**, wal2json **2.6-3**, ZFS **2.4.1-1ubuntu5**. Devices `/dev/vdb` and `/dev/vdc` are guest-side.
- The base backup and archived WAL live **on the host, out-of-band** (incident-scoped via the `archive/current`
  symlink). Restore reads from there into a fresh sandbox cluster; it never reads or writes the victim's live PGDATA.
- DuckDB is the sanctioned analytical query tool. P4 adds **no** new third-party runtime; restore uses stock
  `pg_basebackup`/`pg_ctl` recovery and stock `zfs clone`.
- Deploy root `<repo>`. Everything you create lives under it. **Never write elsewhere on the host.**
- Config is one flat file, `<repo>/etc/lab.env`, sourced by everything. Discover values; never guess.
- The harness deploy root is a git repository. Its HEAD is the harness version recorded in `harness_commit`.

## Operational warnings carried forward — read before you touch anything

1. **Never restore into, or start recovery against, the victim cluster or the victim dataset.** Sandbox instances and
   `zfs clone` only. This is the P4 safety rule and it is mechanically checked.
2. **Stop PostgreSQL before `bin/lab-reset`.** A live cluster causes exit 2 and no rollback. `lab-reset` restarts it.
   (This concerns the victim reset path, not your sandbox cluster, which you manage independently.)
3. **One slot, one consumer, database `labdb`.** Never recreate the slot, and never create a fresh slot to "fix" an
   invalidated one — roll back to a T1/T2 snapshot that still contains it.
4. After a T1/T2 reset the slot rewinds with `PGDATA`; the host ledger does not. Wait for `bin/lab-slot --check`
   exit 0 (use `bin/lab-barrier`) before capturing.
5. Guest `/tmp` is mounted `noexec`. Do not remount it. Work around it.
6. `bin/lab-verify*` do not export sourced keys: invoke as `set -a; source etc/lab.env; set +a; bin/lab-verify`.
7. `bin/lab-consumer status` and `bin/lab-slot --check` need the open incident id; discover it from `archive/current`.
8. **All LSN comparison is integer `(high<<32)+low`, never string.** The `3/9` vs `3/10` ordering trap is real; a
   required test case covers it in candidate/coordinate ordering.
9. Prior contracts are hash-frozen in `logs/review/`. Keep them byte-identical.
10. **Tear down each sandbox cluster and each ZFS clone after validation.** A residual clone or a running sandbox
    cluster left behind can contaminate a later incident or exhaust the pool. Teardown is part of done, and it must
    itself never touch the victim or evidence.

## Rules of engagement

1. **Scope.** Do only the task named in `TASK_TO_EXECUTE`. Do not start the next task, do not "while I'm here" fix
   things, do not refactor files owned by another task. Record any out-of-scope defect in
   `logs/review/<task-id>/observations.md` and continue.
2. **Dependencies.** Verify the `Depends on` tasks in your WI are complete (their review bundles exist and their
   assertions passed). If not, stop and report.
3. **Idempotence.** Every script is safe to re-run: it detects existing correct state and reports `"changed": false`,
   never duplicating data, corrupting the ledger, or leaving an orphaned sandbox/clone.
4. **No invention.** If a value is unknown, discover it and record it in `etc/lab.env`. Never hardcode a guess.
5. **Determinism (Article I).** No language model participates anywhere in P4. Restore, validation and verdict are
   deterministic: the same coordinate over the same evidence -> the same verdict, asserted by re-run.
6. **Restore is read-only w.r.t. victim + evidence (the P4 safety rule).** Sandbox clusters and `zfs clone` only;
   never `pg_ctl`/`systemctl` the victim cluster; never `zfs rollback` the victim dataset. Mechanically checked by a
   before/after victim+evidence manifest that must be byte-identical.
7. **Validate is not promote.** Validation runs entirely in the sandbox and never promotes. Promotion is a separate,
   guarded step requiring a clean verdict and an explicit authorization token; in the lab it is a logged simulation.
8. **Detection does not peek, and neither does restore selection.** P4 restores against a coordinate handed to it; it
   may read the oracle manifest **only** to validate the restored state (that is the oracle's scoring role, Article II),
   never to choose or adjust the coordinate.
9. **Stock mechanisms only (Article V).** `pg_basebackup`/`pg_ctl` recovery, `zfs clone`, DuckDB SQL, Python 3, POSIX
   shell. No bespoke restore engine, no ML library, no model call. If you find yourself adding one, stop and report.
10. **Fail loud (Article VIII).** No `|| true` on a check. Every validation/verdict/safety test includes a deliberate
    regression case proving the check detects a violation, then passes again after revert.
11. **Simplicity (Article VI).** Prefer a short script in `bin/` over a package.
12. **Read-only verification gates (Article XVI).** `bin/lab-verify-p4` and any regression run must not create, modify
    or delete anything under the evidence root; proven with `bin/lab-gate-readonly-check`.
13. **Lab containment (Article X).** All data synthetic. No production data, no personal data, no outbound calls.

## MODE semantics

- `MODE: DRY_RUN` — change nothing. Produce `logs/review/<task-id>/dry-run.md` with: the exact commands you intend to
  run in order, the files you intend to create or edit with a one-line purpose each, the preconditions you checked and
  their observed values (including `bin/lab-ready` exit status, the reconciliation status of the target incident, and
  the victim+evidence manifest hash you will compare against afterward), and any ambiguity to resolve before executing.
  Then stop.
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
4. Any sandbox cluster and ZFS clone created by the task has been torn down (unless the WI says to retain it for a
   later task), with teardown proven not to have touched the victim or evidence.
5. The review bundle exists at `logs/review/<task-id>/` containing `commands.log`, `acceptance.md` (one tier-labelled
   row per test), `artefacts.md`, `lab.env.snapshot`, `observations.md`, plus any extra files the WI names.
6. `sdd/specs/P4-restore-validation/checklist.md` has your task's row updated with the date and bundle path. You do
   **not** fill in the `Reviewed` column; the operator owns that.

## Report back

Finish with a short plain-text summary, in this shape and nothing more:

```
TASK: <id> <title>
RESULT: PASS | FAIL | BLOCKED
ARTEFACTS: <n> files
ACCEPTANCE: TIER M <p>/<n> · TIER A <p>/<n>
NEGATIVE TEST: <what you broke on purpose, that the check caught it, and that it passes again after revert>
VICTIM+EVIDENCE UNTOUCHED: <yes/no — manifest byte-identical before and after>
DEVIATIONS: <none | what and why>
BLOCKERS: <none | what you need from the operator>
NEXT: <the next task id, not started>
```

## What the operator will review

Expect a sceptical human who has already caught this project shipping a self-attested green build in several tranches.
They will read your `RESULT` line, then `acceptance.md` checking the tier column, then the negative-test evidence, then
`observations.md`, then spot-check two artefacts by hand. For P4 they will pay closest attention to three things: the
**loop-closing headline** (they will feed the true ground-truth coordinate themselves and confirm the verdict is
`correct` with zero mismatches), the **discrimination negatives** (a post-damage coordinate must NOT validate clean),
and the **victim+evidence-untouched manifest** (they will confirm it is byte-identical before and after a restore).
Write your bundle for a reader who assumes the happy path was not actually tested and that any claim not mechanically
re-derived is unproven.

---
