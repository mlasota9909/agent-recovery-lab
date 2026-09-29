# Checklist — P2: Capture Collectors & the Append-Only Ledger

The agent fills `Date` and `Bundle` when a task completes. **The operator owns the `Reviewed` column** — the agent
never ticks it.

| Task | Title | Date | Bundle | Reviewed |
| --- | --- | --- | --- | --- |
| C001 | Freeze `capture-completeness.md`; record entry gate | 2026-08-21 | `logs/review/C001/` | ☐ |
| C002 | `bin/lab-capture` orchestration + session manifest | 2026-08-21 | `logs/review/C002/` | ☐ |
| C003 | Snapshot loop LSN anchoring → `snapshots.json` | 2026-08-21 | `logs/review/C003/` | ☐ |
| C004 | Filesystem capture (`fs_diff.tsv` + `fs_hashes.tsv`) | 2026-08-21 | `logs/review/C004/` | ☐ |
| C005 | DB stream integrity (before-images + DDL, LSN order) | 2026-08-21 | `logs/review/C005/` | ☐ |
| C006 | `bin/lab-query` no-ETL DuckDB view layer | 2026-08-21 | `logs/review/C006/` | ☐ |
| C007 | `bin/lab-capture-workload` deterministic 500-op workload | 2026-08-21 | `logs/review/C007/` | ☐ |
| C008 | `bin/lab-ledger-account` exactly-once reconciliation | 2026-08-21 | `logs/review/C008/` | ☐ |
| C009 | Capture teardown + slot hygiene | 2026-08-21 | `logs/review/C009/` | ☐ |
| C010 | `bin/lab-verify-p2` gate; contracts re-verified; handoff | 2026-08-21 | `logs/review/C010/` | ☐ |

## Operator review order

1. `RESULT` line of the agent's report.
2. `logs/review/<task>/acceptance.md` — **check the tier column**, not just PASS.
3. The negative-test evidence. Confirm the check went red, then green again after revert.
4. `observations.md` — deviations and out-of-scope findings.
5. Hand spot-check two artefacts. For **C005**, hand-verify one U and one D record's before-image against the known
   pre-change value yourself. For **C008**, pick three operations from `workload.jsonl` and trace each to exactly one
   `db.jsonl` record by hand — confirm no second match exists.

## Acceptance criteria coverage

| AC | Tier | Owning task |
| --- | --- | --- |
| AC-P2-01 | M | C001 |
| AC-P2-02 | M | C002 |
| AC-P2-03 | M | C002 |
| AC-P2-04 | M | C002 |
| AC-P2-05 | M | C003 |
| AC-P2-06 | M | C004 |
| AC-P2-07 | M | C004 |
| AC-P2-08 | M | C005 |
| AC-P2-09 | M | C005 |
| AC-P2-10 | M | C006 |
| AC-P2-11 | M | C007 |
| AC-P2-12 | M | C008 |
| AC-P2-13 | M | C008 |
| AC-P2-14 | M | C008 |
| AC-P2-15 | M | C009 |
| AC-P2-16 | M | C010 |
| AC-P2-17 | M | C010 |
| AC-P2-18 | A | C010 |

Seventeen of eighteen criteria are tier M. The single tier A criterion is the handoff record, which asserts on
machine-readable fields, per Article XIII.

## Tranche exit condition

P2 is accepted when `bin/lab-verify-p2` reports every criterion PASS with per-tier totals printed separately;
`capture-completeness.md` is frozen and hash-verified; `bin/lab-capture` orchestrates all collectors behind the
`lab-ready` gate; every snapshot carries an LSN; before-images and DDL are present in one LSN-ordered `db.jsonl`; the
DuckDB layer answers over the ledger with no ETL and cross-checks against a plain line count; a 500-operation workload
reconciles exactly-once with zero gaps and zero duplicates; the provenance label is absent from every detection path;
slot hygiene is clean at teardown; and the P0/P1/P1.1 gates and contract hashes are unchanged.

## Note for P3

P3's entry condition is a ledger that has passed `bin/lab-ledger-account` (ADR-P2-7). Do not begin analytics (Arm A
ranker) or representation building (Arm B) against a ledger that has not reconciled exactly-once. P3 reads only
`db.jsonl`, `snapshots.json`, `fs_diff.tsv`, `fs_hashes.tsv` via the DuckDB views, and **must not** read the
`principal` provenance field (Article II, §5 of the capture-completeness contract).
