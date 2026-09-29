# Amendment 1 to the frozen results-row contract

Supersedes: `results-row.md`, section `### Coordinates`, the coordinate-object import clause only.

Exact superseded clause (verbatim):

> Each coordinate is an embedded object valid against the frozen `P0-lab-substrate/contracts/coordinate.md`, carrying
> `wall_clock`, `lsn`, `snapshot`, `skew_ms`, `skew_bytes`, `resolved_by`.

References: `ADR-P7.1-6`.
Frozen: yes. Record this file's sha256 in `logs/review/L004/` alongside its consumers.

## Change (additive, backward compatible)
The coordinate `resolved_by` enumeration is extended from:

    { lsn_first, snapshot_first, time_first }

to:

    { lsn_first, snapshot_first, time_first, live_heartbeat }

`live_heartbeat` denotes a coordinate resolved against a live isolated cluster's heartbeat
table during a P7.1 isolated re-run. A coordinate carrying `live_heartbeat` MUST carry a
non-zero measured skew.

## Scope
Authorized for every coordinate object that uses this enum:
`ground_truth_coordinate`, `chosen_coordinate`, `naive_coordinate`,
`incident_open_coordinate`, `incident_close_coordinate`.

## Backward compatibility
The change only ADDS a permitted value. Every previously valid results row remains valid.
No migration is performed. Rows written before this amendment are unaffected. A retained
pre-amendment fixture row using `lsn_first` MUST still validate (negative-compat test).

## Consumers that must read this amendment together with results-row.md
`etc/results-row.schema.json`, `lib/generate_results_schema.py`, `lib/results_schema.py`,
`lib/lab_verify_p1.py`, `WI-L004`, and every gate pinning the schema hash or asserting
"contracts unchanged".
