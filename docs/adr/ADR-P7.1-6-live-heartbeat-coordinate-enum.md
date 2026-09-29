# ADR-P7.1-6: additive `live_heartbeat` value on the coordinate `resolved_by` enum

## Status
Accepted 2026-08-28. Authoritative version supplied by operator to resolve blocker
`P7.1-L004-SCHEMA-01`. If an earlier partial `ADR-P7.1-6` exists in this directory, this
file supersedes and replaces its content. Supersedes the "results-row schema unchanged"
assertions in `run-matrix-plan.amendment-1.md` A6 and `incident-isolation.md` section 8,
to the narrow extent of adding one enum value.

## Context
P7.1 live isolated re-runs resolve recovery coordinates against a live isolated cluster's
heartbeat table and must record `resolved_by: live_heartbeat` with measured skew
(`run-matrix-plan.amendment-1` A2, `incident-isolation` section 7, `WI-L004` L004-1,
`spec` FR-5, AC-P7.1-10). The frozen results-row schema permits only
`lsn_first | snapshot_first | time_first`. The two requirements are unsatisfiable as
written, so `bin/lab-matrix --force` fails validation on the first coordinate it checks:

```text
assertion failed: row rejected: ground_truth_coordinate.resolved_by: 'live_heartbeat' not in ['lsn_first', 'snapshot_first', 'time_first']
```

This is an internal contradiction inside the P7.1 specification, not a bug. The substrate
already resolves live coordinates correctly (SC-02 535 ms, SC-03 2359 ms, SC-04 3942 ms
measured skew); the block is purely at results validation.

## Decision
Extend the coordinate `resolved_by` enum with a fourth value, `live_heartbeat`, as a
distinct resolution source. The change is additive and backward compatible: every
historical row (SC-01 banked rows, the 51 prior P7 rows) remains valid, so no migration
occurs. The value is authorized for all five coordinate objects. Query direction and
evidence source are NOT split into separate fields, because that would be a breaking change
requiring migration of every historical row.

## Consequences
- `results-row.md` stays byte-identical; the change is recorded in `results-row.amendment-1.md`.
- `etc/results-row.schema.json` is regenerated; its new hash is re-pinned across all gates.
- `WI-L004` L004-1 accepts `live_heartbeat` and negatively tests a bogus value and zero skew.
- `run-matrix-plan.amendment-2.md` supersedes the two "schema unchanged" clauses.
- Backward compatibility is proven by a retained pre-amendment `lsn_first` fixture row that
  still validates unchanged.
