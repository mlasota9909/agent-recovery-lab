# Contract — Ledger Integrity

**Status:** FROZEN at end of P1. Load-bearing for P2 (capture), P3 (analytics), P5 (representations), P7 (analysis).

## Why this contract exists

Discovered during the P0.1 acceptance review. The logical replication slot lives inside `PGDATA`, which sits on
`labpool/victim/pgdata` and is therefore **rewound** by a T1 or T2 reset. The host-side evidence ledger is append-only
by design and is **not** rewound.

A reset therefore desynchronises the slot's position from the ledger's contents. Whether that produces duplicated LSN
ranges (the consumer re-reads and re-appends a window it already wrote) or orphaned ranges (a window is recorded that
the rewound victim no longer contains) depends entirely on incident-scoping discipline being applied perfectly, by
hand, across hundreds of unattended runs.

Discipline is not a control. These two invariants are.

## Invariant 1 — Per-incident LSN idempotency

Within the ledger of a single `incident_id`, **no LSN may appear more than once.**

- The unit of comparison is the commit LSN of a decoded change record.
- Duplicate detection is exact-match on the LSN string after normalisation to uppercase `X/YYYYYYYY` form.
- A duplicate is a hard failure, never a warning, and never de-duplicated silently. Silent de-duplication would
  conceal a capture defect and is prohibited by Article VIII.

Rationale: a duplicated range inflates change-volume analytics, which are precisely the signal P3's anomaly scoring
depends on. A duplicate delete burst could manufacture an anomaly that never happened.

## Invariant 2 — Range containment

Every LSN in an incident's ledger MUST lie within the closed interval bounded by that incident's recorded open and
close coordinates:

```
incident_open_coordinate.lsn  <=  ledger LSN  <=  incident_close_coordinate.lsn
```

- Comparison is numeric on `pg_lsn`, computed as `(high << 32) + low`. **Never** string comparison — `3/9` sorts
  above `3/10` lexically and that error would silently corrupt every range check.
- An LSN outside the interval means either the incident boundaries are wrong or the ledger contains evidence from a
  different incident. Both are hard failures.

Rationale: containment is what makes an incident a closed, addressable artefact. Without it, "evaluate this arm
against incident X" has no well-defined evidence set, and ADR-P1-2's fixed-incident property is unenforceable.

## Invariant 3 — Monotonic non-decrease within a stream

Within `db.jsonl` for one incident, commit LSNs MUST be non-decreasing in file order.

- Equal consecutive LSNs are permitted only for distinct change records within the same transaction commit.
- A decrease indicates either an out-of-order append or a post-reset re-append, and is a hard failure.

## Verification

`bin/lab-ledger-verify --incident <id>` asserts all three invariants and emits:

```json
{
  "incident_id": "i_20260820T041005Z_3ba77e",
  "records": 18442,
  "distinct_lsns": 18442,
  "duplicate_lsns": [],
  "open_lsn": "3/A1000000",
  "close_lsn": "3/A3B00000",
  "out_of_range": [],
  "monotonic": true,
  "ok": true
}
```

Exit codes: `0` all invariants hold; `1` one or more violated; `2` missing precondition (no ledger, no incident
record). Violations are enumerated in the output, capped at the first 20 with a total count, so a failure is
diagnosable without dumping the whole ledger.

## Enforcement points

1. `lab-evaluate-arm` calls `lab-ledger-verify` before analysis and **refuses to proceed** on non-zero exit
   (AC-P1-18). The result is recorded in the results row as `ledger_integrity_ok`.
2. `lab-generate-incident` calls it after capture stop, so a defective incident is identified at creation rather than
   after a dozen arms have been run against it.
3. P2's acceptance suite re-runs it over a known 500-operation workload.

## The catch-up barrier

Related but distinct. After any reset, the consumer must catch up before capture begins, or the ledger will be missing
its opening window. `bin/lab-barrier` polls `lab-slot --check` until exit 0, to a bounded timeout, then exits.

- The barrier MUST NOT sleep a fixed guessed interval.
- The barrier MUST exit non-zero on timeout rather than proceeding on a degraded slot.
- Default timeout 120 s, overridable by `--timeout`, recorded in `lab.env` as `BARRIER_TIMEOUT_S`.

A fixed sleep would be an Article VIII violation: it cannot fail, and it hides the condition it is meant to wait for.

## Invariants for readers of this contract

- An incident whose integrity assertions fail is retained as evidence and excluded from analysis. It is never
  repaired in place; it is regenerated.
- These invariants are properties of one incident. They say nothing across incidents, and they must not be used to
  compare LSNs between incidents, because a T1 reset replays the timeline and LSNs recur.

---
Frozen at end of P1. Amendments: none.
