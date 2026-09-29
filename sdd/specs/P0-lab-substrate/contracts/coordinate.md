# Contract — Recovery Coordinate Triple

**Status:** FROZEN 2026-08-17 at end of P0. Load-bearing for P1 (ground truth), P3 (analytics), P4 (restore), P5 (representations).
Changes only by explicit dated amendment.

A recovery coordinate identifies one point in the victim's history across both layers. It is a triple, because
neither layer alone is sufficient: the database can be restored to an arbitrary LSN, the filesystem only to a
snapshot boundary.

## Fields

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `wall_clock` | ISO 8601 UTC, microsecond precision | yes | Human/operator-facing instant |
| `lsn` | string `X/YYYYYYYY` | yes | PostgreSQL WAL position; the authoritative database coordinate |
| `snapshot` | string, ZFS snapshot short name | yes | Newest recursive snapshot of `labpool/victim` at or below `lsn` |
| `skew_ms` | integer, >= 0 | yes | Wall-clock milliseconds between `snapshot` creation and `lsn` |
| `skew_bytes` | integer, >= 0 | yes | WAL bytes between the snapshot's recorded LSN and `lsn` |
| `resolved_by` | enum `lsn_first` \| `snapshot_first` \| `time_first` | yes | Which field was the input to resolution |

## Resolution rules

1. Given an `lsn`, `snapshot` is the newest recursive snapshot whose recorded LSN is **at or below** `lsn`. Never
   above: a snapshot taken after the target position may already contain the damage.
2. Given a `wall_clock`, map to `lsn` using the `lab_heartbeat` series, taking the newest heartbeat at or below the
   instant, then apply rule 1.
3. Given a `snapshot`, `lsn` is that snapshot's recorded LSN and skew is zero by definition.
4. Skew MUST be computed and reported on every resolution. It is a measured experimental quantity, not an error
   condition, and MUST NOT be suppressed, rounded away or defaulted to zero.
5. If no snapshot at or below exists, resolution fails with a non-zero exit. It does not fall back to the oldest
   snapshot.

## JSON form

```json
{
  "wall_clock": "2026-08-17T04:21:09.481223Z",
  "lsn": "3/A2F41C08",
  "snapshot": "s_20260817T042100Z",
  "skew_ms": 9481,
  "skew_bytes": 1179648,
  "resolved_by": "lsn_first"
}
```

## Invariants

- A coordinate is meaningless without its incident context; it is always stored alongside an incident id.
- `skew_bytes` is zero if and only if `lsn` equals the snapshot's recorded LSN.
- Two coordinates are comparable only within the same incident, because a T1 reset replays the timeline.
