# Spec — P4: Restore, Validation & the Promotion Gate

**Feature ID:** P4-restore-validation
**Status:** ready for implementation
**Owner:** Maciej Lasota
**Depends on:** P0/P0.1 (substrate), P1 (oracle + manifest + results row), P2/P2.1 (certified ledger), P3 (SC-01
incident + Arm A/naive coordinates), P3.1 (read-only gates + regression).
**Blocks:** P5 (representations) and P6 (Arm B) reuse the restore+validate harness to turn a model-chosen coordinate
into a scored outcome. P7 (run matrix) drives it at scale.

## 1. Purpose

Close the loop. Take a recovery coordinate and perform the **real** recovery: point-in-time restore of PostgreSQL into
an isolated sandbox cluster, a ZFS clone restore of the filesystem subtree at the resolved snapshot, and a validation
of the restored state against the ground-truth oracle manifest at row, byte and schema level — ending in a
deterministic consistency verdict and a guarded promotion gate. The defining acceptance test: feeding the **known
ground-truth coordinate** must produce a `correct` verdict with zero mismatches. If the perfect coordinate does not
validate clean, the measurement apparatus is wrong and every P3/P6 number is meaningless.

This tranche completes the walking skeleton: P0 through P4 plus SC-01 is a sound, quantitative, end-to-end result.

## 2. Background — what already exists

P4 is restore-and-compare over finished infrastructure. Reuse, do not rebuild:

- `bin/lab-coordinate` — heartbeat->LSN->snapshot resolution (ADR-008): the newest snapshot with LSN <= target.
- The P1 **oracle manifest** — the known-good pre-incident state: per-relation row counts + content hashes, per-file
  byte hashes, schema DDL. This is the comparison oracle for validation.
- The P1 two-phase harness and FROZEN `results-row.md`; `bin/lab-generate-incident`.
- `bin/lab-inject-sc01` + the reconciled SC-01 incident (P3); `bin/lab-rank` (Arm A) and `bin/lab-naive` emitting
  `arm-coordinate` records (P3).
- The host-side base backup + archived WAL (incident-scoped via `archive/current`) — the restore source.
- `bin/lab-ledger-account` (reconciliation entry gate); `bin/lab-ready`, `bin/lab-reset`, `bin/lab-slot`,
  `bin/lab-barrier`; `bin/lab-regression`, `bin/lab-gate-readonly-check` (P3.1).

P4 adds: the two contracts, DB PITR into a sandbox, ZFS clone FS restore, the cross-layer orchestrator, the
row/byte/schema validator, the verdict, the guarded promotion gate, the oracle<->reality agreement check, and the gate.

## 3. Scope

### In scope

- Two frozen contracts: `restore-report.md` (the verdict record) and `promotion-gate.md` (validate-vs-promote +
  sandbox isolation).
- `bin/lab-restore-db` — replay the host base backup + archived WAL to a target LSN into a **new sandbox cluster**
  (own PGDATA + port); never touch the victim cluster.
- `bin/lab-restore-fs` — `zfs clone` the resolved snapshot into a sandbox mountpoint; never `zfs rollback` the victim.
- `bin/lab-restore` — orchestrator: resolve one coordinate to (LSN, snapshot), restore both layers to it, record
  cross-layer skew, assemble the report skeleton.
- `bin/lab-validate` — compare restored DB (per-relation row count + content hash), restored FS (per-file byte hash),
  and restored schema (DDL) against the oracle manifest; emit per-object mismatches classified as `damage_retained`
  or `legit_lost`.
- `bin/lab-verdict` — the deterministic 4-level consistency verdict per `restore-report.md` §5.
- `bin/lab-promote` — the guarded promotion gate: clean verdict + explicit token; lab simulation only.
- The oracle<->reality agreement check (real-restore outcome for Arm A's coordinate matches the P3 oracle's
  analytical score) and the read-only-w.r.t.-victim safety property.
- `bin/lab-verify-p4` tiered gate (itself read-only, Article XVI); prior contract-hash re-verification; regression via
  `bin/lab-regression`; a P4 architecture handoff.

### Out of scope

- Any change to a frozen contract, or any new field on the results row or ledger-integrity contract.
- Representation building R0/R1/R2 and the Arm B query interface (that is **P5**).
- Any model invocation or Arm B harness (that is **P6**).
- SC-02/03/04 injectors and their oracle tuning (later tranches). P4 restores against the SC-01 incident realized in P3.
- Real (non-simulated) promotion. In the lab, promotion is always a logged simulation (`promotion-gate.md` R4).
- Any use of the oracle manifest to *choose* or adjust a coordinate (Article II — manifest is for scoring only).

## 4. Functional requirements

- **FR-1 Contracts + entry gate.** Both P4 contracts are written and hash-frozen. The tranche opens only when
  `bin/lab-ready` exits 0, the target SC-01 incident has passed `bin/lab-ledger-account`, and the coordinate to be
  restored has `selection_inputs.arm_no_peek_ok` true; E001 records all three.
- **FR-2 DB restore.** `bin/lab-restore-db <lsn>` replays the base backup + archived WAL to exactly the target LSN
  into a new sandbox cluster with its own PGDATA and port. It never starts, stops, or writes the victim cluster; the
  victim PGDATA is byte-identical before and after.
- **FR-3 FS restore.** `bin/lab-restore-fs <snapshot>` creates a ZFS clone of the resolved snapshot at a sandbox
  mountpoint. It never rolls back or destroys the victim dataset; the victim dataset is unchanged.
- **FR-4 Cross-layer orchestration.** `bin/lab-restore <coordinate>` resolves one coordinate to (LSN, snapshot) via
  `bin/lab-coordinate` (newest snapshot with LSN <= target), restores both layers to it, and records the cross-layer
  skew in the report.
- **FR-5 Validation.** `bin/lab-validate` compares the restored DB, FS and schema to the oracle manifest and emits
  per-object mismatches classified `damage_retained` or `legit_lost`, plus the integer summary counts.
- **FR-6 Verdict.** `bin/lab-verdict` emits one of `correct` / `incorrect-safe` / `incorrect-corrupt` /
  `not-recovered`, deterministically from the validation results per `restore-report.md` §5.
- **FR-7 Promotion gate.** `bin/lab-promote` refuses unless the verdict is `correct` AND an explicit authorization
  token is supplied; validation never promotes; in the lab a clean+authorized request is a logged simulation that
  leaves the victim and evidence untouched.
- **FR-8 Agreement + safety.** For Arm A's coordinate, the real-restore outcome (damage retained / legit lost) agrees
  with the P3 oracle's analytical score; and a whole-of-victim-plus-evidence manifest is byte-identical before and
  after a full restore+validate cycle.
- **FR-9 Loop-closing headline + discrimination.** Feeding the ground-truth coordinate yields `correct` with zero
  mismatches; feeding a post-damage coordinate yields a non-`correct` verdict with damage retained; feeding a
  too-early coordinate yields `incorrect-safe` with legitimate loss.
- **FR-10 Gate + handoff.** `bin/lab-verify-p4` runs every P4 check with per-tier totals and is itself read-only over
  the evidence root; all prior contract hashes re-verify unchanged; `bin/lab-regression` is green; a P4 handoff records
  the restore mechanism, observed skew, the loop-closing result, the walking-skeleton milestone, and correctly states
  P5 builds R0/R1/R2 and P6 builds Arm B.

## 5. Acceptance criteria

| ID | Tier | Requirement |
| --- | --- | --- |
| AC-P4-01 | M | Both P4 contracts exist, are well-formed, and are hash-frozen in `logs/review/E001/`; `lab-ready` exit 0, the SC-01 incident's exactly-once reconciliation, and the target coordinate's `arm_no_peek_ok=true` are recorded as the entry gate |
| AC-P4-02 | M | `bin/lab-restore-db <lsn>` restores to a new sandbox cluster (own PGDATA + port) and never writes the victim cluster: victim PGDATA content hash is byte-identical before and after |
| AC-P4-03 | M | The restored cluster's replay stops at exactly the target LSN: `pg_last_wal_replay_lsn()` <= target and the first commit beyond target is absent from the restored data |
| AC-P4-04 | M | `bin/lab-restore-fs <snapshot>` creates a `zfs clone` at a sandbox mountpoint and never rolls back/destroys the victim dataset: the victim dataset's current content hash is unchanged, and no `zfs rollback` of a `victim` dataset appears in the command log |
| AC-P4-05 | M | `bin/lab-restore` resolves one coordinate to (LSN, snapshot) with the snapshot being the newest with `lsn_int <= target` (integer arithmetic; a `3/9` vs `3/10` case is covered), restores both layers, and records `coordinate.skew_ms` in the report |
| AC-P4-06 | M | `bin/lab-validate` compares each relation's row count and content hash to the oracle manifest and lists per-relation mismatches |
| AC-P4-07 | M | `bin/lab-validate` compares each file's byte hash to the oracle manifest and lists per-file mismatches (including missing/extra) |
| AC-P4-08 | M | `bin/lab-validate` compares restored schema DDL to the oracle manifest; a deliberately altered relation definition is detected as a schema diff |
| AC-P4-09 | M | `bin/lab-verdict` emits exactly one of the four fixed verdicts, deterministically from the validation results (two runs byte-identical); mapping follows `restore-report.md` §5 |
| AC-P4-10 | M | The assembled restore report conforms to `restore-report.md` (all required fields present, types correct, example-schema-valid) and its `harness_commit` is the git HEAD computed on a clean tree at report time |
| AC-P4-11 | M | `bin/lab-promote` refuses when the verdict is not `correct`, and refuses when no authorization token is supplied; both refusals are non-zero exit with a stated reason |
| AC-P4-12 | M | With a `correct` verdict AND a valid token, `bin/lab-promote` records `decision=simulated`, performs no destructive action, and never emits `decision=authorized` in the lab; running validation alone leaves `promotion.decision=withheld` |
| AC-P4-13 | M | **Loop-closing headline:** restoring the TRUE ground-truth coordinate yields `consistency_verdict=correct` with `damage_rows_retained=0`, `legit_rows_lost=0`, `files_mismatched=0`, `schema_diffs=0`, all read from the restore report. If it does not validate clean, the task FAILs |
| AC-P4-14 | M | **Discrimination:** restoring a post-damage coordinate yields a non-`correct` verdict with `damage_rows_retained>0`; restoring a too-early coordinate yields `incorrect-safe` with `legit_rows_lost>0`. Validation demonstrably discriminates |
| AC-P4-15 | M | **Oracle<->reality agreement:** for Arm A's coordinate, the real-restore `summary.damage_rows_retained` and `legit_rows_lost` equal the P3 oracle's analytical score for the same coordinate |
| AC-P4-16 | M | **Safety property:** a whole-of-victim-plus-evidence manifest (victim PGDATA + victim dataset + evidence root) is byte-identical before and after a full restore+validate cycle; `safety.victim_untouched` and `safety.evidence_untouched` are both `true` in the report |
| AC-P4-17 | M | `bin/lab-verify-p4` reports every criterion PASS with per-tier totals printed separately, exit 0, and is itself read-only over the evidence root (proven by `bin/lab-gate-readonly-check`) |
| AC-P4-18 | M | All prior gates still green (`lab-verify` 18/18, `-p1` 24/24, `-p1.1` 16/16, `-p2` 18/18, `-p2.1` 16/16, `-p3` 19/19, `-p3.1` 16/16); every prior contract hash unchanged incl. `capture-completeness.md` byte-identical; `bin/lab-regression` green against pinned fixtures |
| AC-P4-19 | A | The P4 handoff records the restore mechanism (PITR + ZFS clone), the observed cross-layer skew, the loop-closing result, the walking-skeleton milestone reached, and states P5 builds R0/R1/R2 and P6 builds Arm B (asserted on machine-readable fields; anti-goal-inversion guarded) |

Eighteen of nineteen criteria are tier M. The single tier A criterion is the handoff record, which asserts on
machine-readable fields, per Article XIII.

## 6. Definition of done

`bin/lab-verify-p4` green with per-tier totals and proven read-only; both P4 contracts frozen; DB PITR into a sandbox
and FS `zfs clone` both proven non-destructive to the victim; cross-layer coordinate resolution with recorded skew;
row/byte/schema validation against the oracle manifest; the deterministic 4-level verdict; the guarded promotion gate
(clean verdict + explicit token, lab simulation only); the loop-closing headline (true coordinate -> `correct`, zero
mismatches); the discrimination negatives; oracle<->reality agreement for Arm A; the victim+evidence-untouched safety
property; every sandbox cluster and clone torn down; all prior gates, regression and contract hashes unchanged; the P4
handoff written without anti-goal inversion. Walking-skeleton milestone (P0-P4 + SC-01) reached.
