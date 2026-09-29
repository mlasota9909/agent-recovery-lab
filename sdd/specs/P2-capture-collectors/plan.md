# Plan — P2: Capture Collectors & the Append-Only Ledger

## Architecture decisions (locked)

These continue the ADR lineage from the roadmap (ADR-006 filesystem via `zfs diff`/`.zfs`; ADR-007 DB via
`pg_recvlogical`+`wal2json`; ADR-008 the cross-layer coordinate) and the storage decision that the ledger is a
directory of files read in place by DuckDB. P2 adds the decisions specific to assembling them.

### ADR-P2-1 — one append-only ledger directory per incident, files not a database

Each incident's evidence is a directory of append-only files: `db.jsonl` (DB changes, DDL and heartbeats, in one
LSN-ordered stream), `snapshots.json`, `fs_diff.tsv`, `fs_hashes.tsv`, plus the session manifest and the workload
operation log. Collectors only ever append; they never rewrite history. This is what makes the ledger auditable and
what lets a T1/T2 reset rewind victim state while the host-side ledger persists. Derived artefacts (DuckDB views,
any Parquet) are rebuildable and may be deleted and regenerated; the raw ledger may not. This preserves the P1
ledger-integrity invariants (no duplicate LSN within an incident; ledger range contained by incident open/close).

### ADR-P2-2 — DuckDB is a read-only view layer, never the store of record

DuckDB binds views directly to the ledger files (`read_json_auto`, `read_csv`) and runs SQL over them with no import
step. It is sanctioned under Article V as a stock analytical tool (single binary, no server), but only as a lens. If
DuckDB and the raw files ever disagree, the files win. No collector writes through DuckDB. This keeps the store of
record plain, greppable and independent of any query-tool version.

### ADR-P2-3 — the snapshot loop anchors every snapshot to a WAL LSN

At each snapshot the loop calls `pg_switch_wal()` and records the resulting/next LSN alongside the snapshot name and
wall clock. This is the mechanism that makes ADR-008's cross-layer coordinate real: a chosen DB LSN resolves to the
newest snapshot at or below it, and the skew is a recorded quantity. A snapshot without an LSN is worthless for
cross-layer recovery, so a null LSN is a hard failure (FR-3), not a warning.

### ADR-P2-4 — filesystem evidence is snapshot-derived, never a live daemon

`fs_diff.tsv` comes from `zfs diff` between consecutive snapshots; `fs_hashes.tsv` from hashing files read out of
`.zfs/snapshot/<snap>/`. No `fanotify`/`inotify` daemon exists in the measured path. The honest consequence is that
filesystem recovery granularity is bounded by the snapshot interval — this is a **measured property**, reported per
run, not a defect. It is exactly the constraint SC-02 exists to expose in a later tranche.

### ADR-P2-5 — provenance is captured but quarantined from detection

The workload generator runs legitimate operations as `lab_app` and damage as `lab_agent`, and the ledger records the
originating principal as a fact so the oracle and `lab-ledger-account` can classify a change as legitimate or damage
**for scoring**. But the analytics-facing surface must not see it. `lab-query`'s default views and `lab-ledger-account`'s
detection path exclude the principal field; only the scoring path reads it. AC-P2-14 enforces this. This is Article II
carried into the capture layer, and it is why the reconciliation is a fair test rather than a leak of the answer key.

### ADR-P2-6 — a generic mixed workload, not a scenario

P2 proves the ledger with a generic, seedable mixed workload (INSERT/UPDATE/DELETE + DDL), **not** with SC-01..04
damage logic. The scenarios belong to later tranches and to the oracle's per-scenario tuning. Conflating them here
would couple ledger-correctness to scenario-correctness and make a failure ambiguous. The workload's only job is to
exercise every ledger path and give `lab-ledger-account` a known operation set to reconcile exactly-once.

### ADR-P2-7 — P2 is entered behind `lab-ready`, and exited behind exactly-once

Entry: `bin/lab-ready` exit 0 (inherited from ADR-P1.1-4). Exit: `bin/lab-ledger-account` proving exactly-once
coverage of a 500-operation workload. Neither is a prose assertion; both are mechanical gates. P3 inherits the exit
condition — it may not begin analytics against a ledger that has not passed reconciliation.

## No new constitutional article

P0.1, P1 and P1.1 each added an article because each was a remediation that surfaced a defect class (XII test
hatches, XIII verification tiers, XIV provenance of record). P2 is a forward build and surfaces no new class; it
operates under the fourteen articles in force. If P2's own acceptance review finds a defect the gate missed, that is
where the next article would come from — not before.

## Task breakdown

| Task | Owns | Serves |
| --- | --- | --- |
| C001 | `capture-completeness.md` contract; entry-gate record | FR-1 |
| C002 | `bin/lab-capture` orchestration | FR-2 |
| C003 | snapshot loop LSN anchoring → `snapshots.json` | FR-3 |
| C004 | `fs_diff.tsv` walker + `fs_hashes.tsv` tree hasher | FR-4 |
| C005 | DB stream integrity (before-images + DDL, LSN order) | FR-5 |
| C006 | `bin/lab-query` DuckDB view layer | FR-6 |
| C007 | `bin/lab-capture-workload` deterministic mixed workload | FR-7 (input) |
| C008 | `bin/lab-ledger-account` exactly-once reconciliation | FR-7 |
| C009 | capture teardown + slot hygiene | FR-8 |
| C010 | `bin/lab-verify-p2` gate; contract re-verify; handoff | FR-9 |

## Sequencing

C001 first (contract + entry gate before any collector). C002 brings up the session and depends on C001. C003 and
C004 complete the snapshot and filesystem streams and depend on C002. C005 verifies the DB stream and depends on
C002. C006 (query layer) depends on the streams existing (C003–C005). C007 (workload) depends on C002. C008
(reconciliation) is the keystone and depends on C003–C007. C009 (teardown) depends on C002. C010 gates and runs last.

```
C001 -- C002 --+-- C003 --+
               |          |
               +-- C004 --+-- C006 --+
               |          |          |
               +-- C005 --+          +-- C008 -- C010
               |                     |
               +-- C007 -------------+
               |
               +-- C009 ------------------------ C010
```

## Risks

- **A collector appears up but is silently not appending** (the P0.1 slot-invalidation class). Mitigated by
  `lab-capture status` re-deriving liveness from unit state *and* file growth, and by `lab-ledger-account` catching a
  coverage gap regardless of what `status` claimed.
- **Before-images silently lost** if `REPLICA IDENTITY FULL` regresses on a relation. This is the highest-consequence
  silent failure in the tranche (it destroys damaged-data scoring). C005's negative test sets `REPLICA IDENTITY
  DEFAULT` and proves the before-image disappears, so a regression breaks a pre-existing assertion.
- **DuckDB version drift** changing `read_json_auto` behaviour. Mitigated by ADR-P2-2: the files are the store of
  record; DuckDB is a lens whose output is always cross-checkable against a plain line count (AC-P2-10).
- **Provenance leak into detection.** Mitigated by ADR-P2-5 and AC-P2-14; inherited by P3.
- **Snapshot interval too coarse to resolve a fast incident.** Not a defect — reported as the filesystem-granularity
  property (ADR-P2-4) and revisited when SC-02 is built.
