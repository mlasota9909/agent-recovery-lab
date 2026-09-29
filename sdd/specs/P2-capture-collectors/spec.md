# Spec — P2: Capture Collectors & the Append-Only Ledger

**Feature ID:** P2-capture-collectors
**Status:** ready for implementation
**Owner:** Maciej Lasota
**Depends on:** P1 (accepted), P1.1 (accepted; `bin/lab-ready` is the entry gate)
**Blocks:** P3 (derived analytics + Arm A deterministic ranker) — P3 reads only what P2's ledger contains

## 1. Purpose

Assemble the individual capture mechanisms into one coherent, append-only evidence ledger per incident, present it as
a no-ETL query layer, and **prove the ledger is complete and exactly-once** against a known workload. After P2, an
incident window yields a ledger from which the ground-truth oracle (P1) and the analytics (P3) can resolve a recovery
coordinate across the filesystem and database layers with no gaps and no double-counting.

## 2. Background — what already exists

P2 is largely integration, not green-field. These exist and must be reused, not rebuilt:

- `bin/lab-consumer` — the `pg_recvlogical` + `wal2json` logical-decoding stream to `db.jsonl`, managed as a
  `lab-consumer@<incident>` systemd unit (P0.1 R003).
- `bin/lab-heartbeat-writer` — the one-second `lab_heartbeat` writer (P0 T014-era).
- `bin/lab-snapshot` / `bin/lab-snapshots` — ZFS snapshot helpers.
- the `zfs diff` helpers (`bin/lab-zfs-diff-json` and friends) and their proof harness.
- `lab_ddl_audit` event trigger, `SECURITY DEFINER`, installed by `bin/lab-schema-init`, part of the publication so
  DDL appears in the decoded stream.
- `bin/lab-barrier`, `bin/lab-slot`, `bin/lab-ready`, `bin/lab-coordinate` (heartbeat→LSN→snapshot resolution),
  `bin/lab-generate-incident`, `bin/lab-ledger-verify` (P1 idempotency/range checks on the ledger).

P2 builds the **orchestration, the filesystem tree hasher, the DuckDB view layer, the deterministic workload
generator and the exactly-once reconciliation**, and completes the snapshot loop's LSN anchoring.

## 3. Scope

### In scope

- A single frozen contract, `capture-completeness.md`, defining the per-incident evidence file set and the meaning of
  "complete and exactly-once".
- `bin/lab-capture {start|stop|status}` — coherently starts and stops all collectors for an incident window and
  records a session manifest; enforces the `lab-ready` entry gate on start.
- Completing the snapshot loop so every entry in `snapshots.json` carries a snapshot name, a wall-clock time and the
  WAL LSN captured with `pg_switch_wal()` at snapshot time (ADR-008 cross-layer coordinate).
- Filesystem capture into the ledger: a `zfs diff` walker producing `fs_diff.tsv` for each consecutive snapshot pair,
  and a tree hasher reading `.zfs/snapshot/<snap>/` producing `fs_hashes.tsv`.
- Verifying DB-stream integrity: before-images present on every UPDATE and DELETE (`REPLICA IDENTITY FULL`), DDL
  present via `lab_ddl_audit`, all in one LSN-ordered `db.jsonl`.
- `bin/lab-query` — a DuckDB read layer presenting `db.jsonl`, `snapshots.json`, `fs_diff.tsv`, `fs_hashes.tsv` and
  the heartbeat rows as views, with no copy/ETL step.
- `bin/lab-capture-workload` — a deterministic, seedable mixed workload (INSERT/UPDATE/DELETE and at least one
  DDL), each operation labelled with its originating principal (`lab_app` legitimate vs `lab_agent`), producing a
  machine-readable operation log to reconcile against.
- `bin/lab-ledger-account` — reconciles the workload operation log against the ledger and asserts exactly-once
  coverage, monotonic LSN, before-image presence, DDL presence, heartbeat→LSN resolvability within one second, and
  every snapshot carrying an LSN.
- Capture teardown + slot hygiene: on `lab-capture stop`, lag returns to zero and the slot is dropped cleanly; the
  incident's ledger and snapshots are retained.
- `bin/lab-verify-p2` — the tiered gate for this tranche; re-verification of P0/P1 contract hashes; a P2 architecture
  handoff document.

### Out of scope

- Any change to a frozen contract, or any new field on the results row or ledger-integrity contract.
- Any analytics, ranking, representation, retrieval interface, or model invocation (P3+).
- Real point-in-time restore or restored-state validation (P4).
- SC-02/03/04 damage logic and the oracle's per-scenario tuning — P2 uses a **generic mixed workload** whose only
  purpose is to exercise and prove the ledger, not a scenario.
- Any use of the provenance label as a detection or ranking signal (Article II).

## 4. Functional requirements

- **FR-1 Contract + entry gate.** `capture-completeness.md` is written and hash-frozen. The tranche opens only when
  `bin/lab-ready` exits 0; C001 records that fact.
- **FR-2 Orchestration.** `bin/lab-capture start <incident>` refuses unless `lab-ready` exits 0, then brings up the
  consumer, heartbeat writer and snapshot loop, and writes a session manifest naming every collector, its PID/unit
  and its output file. `stop` brings them down in the reverse order and runs teardown (FR-8). `status` prints the
  live state of each collector as JSON. It mutates only collector lifecycle and the ledger, never victim data.
- **FR-3 Snapshot LSN anchoring.** Every `snapshots.json` entry has `{snapshot, wall_clock, lsn}` where `lsn` is the
  value returned by `pg_switch_wal()`/`pg_current_wal_lsn()` at snapshot time. No entry may have a null LSN.
- **FR-4 Filesystem capture.** For each consecutive snapshot pair, `fs_diff.tsv` records one row per changed path with
  the `zfs diff` change type (`+ - M R`) and the path; `fs_hashes.tsv` records `{snapshot, path, sha256}` for the
  protected subtree read from `.zfs/snapshot/<snap>/`. No `fanotify`/`inotify`; no `zfs send`.
- **FR-5 DB stream integrity.** In `db.jsonl`, every UPDATE and DELETE carries the old tuple (before-image); every
  `CREATE`/`ALTER`/`DROP` on a scenario relation appears via `lab_ddl_audit`; records are in non-decreasing LSN order.
- **FR-6 Query layer.** `bin/lab-query <incident> "<sql>"` runs DuckDB SQL over views bound directly to the ledger
  files (no import step). At minimum it exposes views `db_changes`, `heartbeats`, `snapshots`, `fs_diff`, `fs_hashes`.
- **FR-7 Reconciliation.** Given a workload operation log and an incident ledger, `bin/lab-ledger-account` asserts:
  every logged operation maps to **exactly one** ledger record (no gaps, no duplicates); LSN order is monotonic;
  before-images present for all U/D; DDL present; for any heartbeat the LSN resolves to within one second; every
  snapshot carries an LSN. It prints a JSON report and exits non-zero on any violation.
- **FR-8 Teardown + hygiene.** After `lab-capture stop`, `bin/lab-slot --check` shows lag at zero and the slot
  dropped; the ledger files and `snapshots.json` remain intact and append-only. Re-running teardown is idempotent.
- **FR-9 Gate + handoff.** `bin/lab-verify-p2` runs every P2 acceptance check with per-tier totals; P0/P1 contract
  hashes are re-verified unchanged; a P2 architecture handoff documents the ledger layout and the reconciliation
  result.

## 5. Acceptance criteria

| ID | Tier | Requirement |
| --- | --- | --- |
| AC-P2-01 | M | `capture-completeness.md` exists, is well-formed, and is hash-frozen in `logs/review/C001/`; `bin/lab-ready` exit 0 is recorded as the entry gate |
| AC-P2-02 | M | `bin/lab-capture start` refuses (exit non-zero) when `bin/lab-ready` exits non-zero, naming the failed readiness condition |
| AC-P2-03 | M | `bin/lab-capture start <incident>` brings up consumer + heartbeat + snapshot loop and writes a session manifest listing each collector, its unit/PID and its output file |
| AC-P2-04 | M | `bin/lab-capture status` reports every collector `active` as JSON during a capture window |
| AC-P2-05 | M | Every entry in `snapshots.json` has a non-null `lsn`; a scripted run produces ≥2 snapshots and all carry an LSN |
| AC-P2-06 | M | `fs_diff.tsv` records the exact set of paths changed between two snapshots (verified against a known filesystem mutation); change types are among `+ - M R` |
| AC-P2-07 | M | `fs_hashes.tsv` sha256 for an unchanged file is identical across two snapshots and differs after a known content change |
| AC-P2-08 | M | In `db.jsonl`, a known UPDATE and a known DELETE each carry the correct **before-image** (old tuple equals the pre-change value) |
| AC-P2-09 | M | A `DROP TABLE` and an `ALTER TABLE` on a scenario relation both appear in `db.jsonl` via `lab_ddl_audit`, in LSN order |
| AC-P2-10 | M | `bin/lab-query <incident> "select count(*) from db_changes"` returns a count matching a direct line-count of `db.jsonl` change rows, with no ETL/import step in the code path |
| AC-P2-11 | M | `bin/lab-capture-workload` is deterministic: two runs with the same seed produce byte-identical operation logs; each operation is labelled with its originating principal |
| AC-P2-12 | M | `bin/lab-ledger-account` maps every one of a 500-operation workload to **exactly one** ledger record — zero gaps, zero duplicates — and exits 0 |
| AC-P2-13 | M | `bin/lab-ledger-account` asserts monotonic LSN, before-images on all U/D, DDL presence, heartbeat→LSN within 1 s, and every snapshot carrying an LSN; all pass |
| AC-P2-14 | M | The analytics-facing view/consumer of the ledger **cannot read** the provenance label: a check confirms `lab-ledger-account` and `lab-query`'s default views exclude the principal field from detection paths (Article II) |
| AC-P2-15 | M | After `bin/lab-capture stop`, `bin/lab-slot --check` shows lag 0 and the slot dropped; `db.jsonl` and `snapshots.json` remain intact |
| AC-P2-16 | M | `bin/lab-verify-p2` reports every criterion PASS with per-tier totals printed separately, exit 0 |
| AC-P2-17 | M | `bin/lab-verify` still 18/18, `bin/lab-verify-p1` 24/24, `bin/lab-verify-p1.1` 16/16; P0/P1 contract hashes unchanged |
| AC-P2-18 | A | The P2 architecture handoff records the ledger layout and the 500-op reconciliation result (asserted on machine-readable fields, not prose) |

All criteria are tier M except AC-P2-18, which attests a one-time documentation event and still asserts on JSON
fields, per Article XIII.

## 6. Definition of done

`bin/lab-verify-p2` green with per-tier totals; `capture-completeness.md` frozen; `bin/lab-capture` orchestrating all
collectors behind the `lab-ready` gate; snapshots LSN-anchored; filesystem and DB streams captured with before-images
and DDL; DuckDB query layer live with no ETL; a 500-operation workload reconciled exactly-once; slot hygiene clean at
teardown; prior contracts hash-verified unchanged; P2 handoff written.
