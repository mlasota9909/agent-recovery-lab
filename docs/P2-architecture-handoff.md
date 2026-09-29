# P2 Capture Collectors — Architecture Handoff (tranche close)

**Date:** 2026-08-21  
**Status:** P2 COMPLETE — `bin/lab-verify-p2` **TIER M: 17/17 · TIER A: 1/1 · TOTAL: 18/18**, exit 0  
**Entry:** `bin/lab-ready` exit 0 (ADR-P1.1-4 / ADR-P2-7)  
**Exit:** `bin/lab-ledger-account` exactly-once (ADR-P2-7)  
**Human review:** `sdd/specs/P2-capture-collectors/checklist.md` Reviewed column still ☐.

Load this file **together with** `docs/P1.1-architecture-handoff.md`, `docs/P1-architecture-handoff.md`, `docs/P0.1-architecture-handoff.md`, and `docs/P0-architecture-handoff.md`.

P3 builds **analytics (Arm A)** and **representations (Arm B)**. P2 deliberately did not.

```json
{
  "ops": 500,
  "mapped": 500,
  "gaps": 0,
  "duplicates": 0,
  "incident": "SC-01_20260820T051544Z",
  "snapshot_interval_s": 5,
  "duckdb": "1.3.2",
  "entry_gate": "lab-ready",
  "exit_gate": "lab-ledger-account",
  "capture_completeness_sha256": "59aeaa61281f211046b953a0641de72dc55c3f6cecc7278ee45802d41003d647"
}
```

---

## 1. Where the build stands

```
P0   substrate ............ DONE
P0.1 remediation ......... DONE
P1   instruments .......... DONE
P1.1 remediation ......... DONE
P2   capture .............. DONE (this file)
P3   analytics + Arm A .... NEXT — burst density, anomaly scoring, candidates, ranker
P4   restore .............. real PITR
P5   representations ...... R0/R1/R2
P6   Arm B ................ modest local model
```

P2 built **no ranker, no representation, no model, no real restore, no SC-02/03/04 damage**. Frozen P0/P1 contracts were not changed. No field was added to the results row.

---

## 2. Per-incident ledger (contract §1)

Host path remains `evidence/<scenario>/<incident>/` (P0/P1), not `${EVIDENCE_ROOT}/<id>/`. File names:

| File | Producer |
| --- | --- |
| `db.jsonl` | `lab-consumer` wal2json format-version 2 (not rewritten) |
| `snapshots.json` | C003 loop `{snapshot, wall_clock, lsn}` JSON array |
| `fs_diff.tsv` | `lab-fs-capture diff` |
| `fs_hashes.tsv` | `lab-fs-capture hash` |
| `session.json` | `lab-capture` |
| `workload.jsonl` | `lab-capture-workload` |

P0 archive `snapshots.json` (reset labels, `recorded_lsn`) is separate.

Logical kinds over wal2json: **change** = I/U/D excluding heartbeat/ddl_audit; **ddl** = inserts to `lab_ddl_audit`; **heartbeat** = inserts to `lab_heartbeat`. `B` records carry the commit LSN *before* the change LSN — C-4 follows P1 (action `C` only).

---

## 3. Collectors

| Collector | Unit / process | Output |
| --- | --- | --- |
| consumer | `lab-consumer@<incident>.service` | `db.jsonl` |
| heartbeat | guest `lab-heartbeat.service` | `lab_heartbeat` → stream |
| snapshot loop | host `lab-snapshot-loop --incident` | evidence `snapshots.json` |

Orchestrator: `bin/lab-capture {start|stop|status}`. Start refuses unless `lab-ready` exits 0. Stop drains (`lab-barrier`), stops collectors, `lab-slot --drop`. Never `lab-slot --create`.

`SNAP_INTERVAL_S=5`. Filesystem recovery granularity follows that interval (ADR-P2-4) — a measured property, not a defect.

---

## 4. Query layer

`bin/lab-query <incident> "<sql>"` — DuckDB CLI `DUCKDB_BIN` views bound to files (`read_json_auto`, `read_csv`). No ETL store of record. Default `db_changes` does **not** project `principal`.

---

## 5. Exactly-once

`bin/lab-ledger-account` maps workload ops to ledger records without reading `principal`. 500/500/0/0 as above. Mapping is greedy 1:1 on `(table, action, natural_key)` / DDL `(command_tag, object_identity)` because wal2json v2 did not emit `xid` on this plugin.

P3 **must not** begin analytics against a ledger that has not passed this gate. P3 **must not** read `principal` (Article II, contract §5).

---

## 6. Do not re-litigate

- Article XIV, ADR-P1.1-1..4, ADR-P2-1..7
- One slot `lab_slot` in `labdb`. Invalidated `wal_removed` → T1/T2 rollback, never a new slot
- Stop PostgreSQL before `lab-reset`
- Guest `/tmp` noexec
- Frozen hashes: P0 R007, P1 W002, C001 `59aeaa61…`

---

## 7. Operational notes for P3

1. After C009 the slot was dropped; it was restored by `docs/runbook-slot-recovery.md` t2. That rewind **re-appends catch-up** onto host `db.jsonl` (duplicate LSNs). The 500-op proof is the C008 report, not a later re-run on the polluted stream.
2. `bin/lab-ready` is again the live-lab gate. P3 entry for *analytics* is `lab-ledger-account` on a **closed** incident ledger, not a growing catch-up file.
3. Workload table `public.p2_probe` is capture-exercise only, not an SC scenario.

---

## 8. P3 anti-goals (do not invert)

P3 **does** build Arm A analytics/ranking and Arm B representation builders. P2 **did not**. P3 still must not: rewrite ledger schema, add a results-row field, use provenance for detection, parse WAL, run a live inotify/fanotify daemon, or treat DuckDB as store of record.
