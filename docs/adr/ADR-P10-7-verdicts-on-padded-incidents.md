# ADR-P10-7 — Verdicts on padded incidents: unchanged P4 for real rows, ledger replay for padded rows

Status: accepted 2026-09-24 (P10 Q001, before any scaling data)
Authority: Article XX.1; C3 of the frozen generator contract ("scored by the P4 oracle path").
Amendment: `scale-generator.amendment-1.md` A4.

## Context

C3 requires every accepted coordinate to be scored by the P4 restore-validate path. P4
restores the physical SC-01 archive, and padded rows were never written to any database.
A physical restore therefore cannot see them, and pointing P4 at the padded evidence root
would report every padded row as "missing" at every restore point.

## Decision

The verdict for an accepted coordinate L has two parts.

1. **P4 part.** The unchanged `p4_score` is run against the frozen evidence root: sandbox
   restore of the real archive at L, validate, verdict, teardown. It uses the same cache
   (`var/restore/<incident>/ab-<lsn>/`) as P9. This decides damage retained, real
   legitimate rows lost, and consistency.
2. **Ledger part.** Apply P4's own lost-row rule and unit (`lab_validate`: sum of
   `row_count` over manifest records with chosen < commit_lsn ≤ optimum) to the padded
   manifest records.

`incorrect_corrupt` and `not_recovered` from P4 stand. Lost-row counts are added in one
unit, and the two components are reported separately.

Padded commits are recorded only at real driver checkpoints (or at close). So at any
chosen point at or after the optimum the padded loss is 0. Below the optimum, the
optimum's own real batch is already lost, so P4 does not return `correct`. Padding
therefore cannot change a verdict class. A guard (P4 `correct` with padded loss > 0 →
`incorrect_safe`) is kept and flagged if it ever fires, because that would contradict
this derivation.

This revision follows the Q001 independent review, which found that the first version
mixed units: distinct padded ids against P4's per-operation counts.

## Consequences

- The real-row half of every verdict is physically validated, as in P9. The padded half
  is a deterministic replay of the padded ledger, and is reported separately in the
  detail sidecar so either half can be audited.
- Padding cannot change a verdict class. It only adds to the lost-row count below the
  optimum. It can never create or hide damage.
