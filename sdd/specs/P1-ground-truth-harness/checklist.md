# Checklist — P1: Ground Truth, Results Contract and Run Harness

The agent fills `Date` and `Bundle` when a task completes. **The operator owns the `Reviewed` column** — the agent
never ticks it.

| Task | Title | Date | Bundle | Reviewed |
| --- | --- | --- | --- | --- |
| W001 | Preconditions verified; handoff anti-goals corrected | 2026-08-20 | `logs/review/W001/` | ☐ |
| W002 | Results-row and ledger-integrity contracts frozen | 2026-08-20 | `logs/review/W002/` | ☐ |
| W003 | Results writer and validator | 2026-08-20 | `logs/review/W003/` | ☐ |
| W004 | Ledger integrity CLI and reset barrier | 2026-08-20 | `logs/review/W004/` | ☐ |
| W005 | SC-01 legitimate workload and commit manifest | 2026-08-20 | `logs/review/W005/` | ☐ |
| W006 | SC-01 injector | 2026-08-20 | `logs/review/W006/` | ☐ |
| W007 | Ground-truth oracle | 2026-08-20 | `logs/review/W007/` | ☐ |
| W008 | Two-phase harness, stubs, null run | 2026-08-20 | `logs/review/W008/` | ☐ |
| W009 | Cycle time re-measured; sample-size plan | 2026-08-20 | `logs/review/W009/` | ☐ |
| W010 | P1 acceptance gate and memo | 2026-08-20 | `logs/review/W010/` | ☐ |

## Operator review order

Read in this order, and read W002 and W007 line by line:

1. `RESULT` line of the agent's report.
2. `logs/review/<task>/acceptance.md` — **check the tier column**, not just PASS.
3. The negative-test evidence. Confirm the check actually went red, then green again after revert.
4. `observations.md` — deviations and out-of-scope findings.
5. Hand spot-check two artefacts.

## Acceptance criteria coverage

| AC | Tier | Owning task |
| --- | --- | --- |
| AC-P1-01 | M | W003 |
| AC-P1-02 | M | W003 |
| AC-P1-03 | M | W003 |
| AC-P1-04 | M | W004 |
| AC-P1-05 | M | W004 |
| AC-P1-06 | M | W004 |
| AC-P1-07 | M | W004 |
| AC-P1-08 | M | W005 |
| AC-P1-09 | M | W006 |
| AC-P1-10 | M | W007 |
| AC-P1-11 | M | W007 |
| AC-P1-12 | M | W007 |
| AC-P1-13 | M | W007 |
| AC-P1-14 | M | W007 |
| AC-P1-15 | M | W008 |
| AC-P1-16 | M | W008 |
| AC-P1-17 | M | W008 |
| AC-P1-18 | M | W008 |
| AC-P1-19 | M | W008 |
| AC-P1-20 | M | W008 |
| AC-P1-21 | M | W009 |
| AC-P1-22 | A | W009 |
| AC-P1-23 | M | W010 |
| AC-P1-24 | M | W010 |

Twenty-three of twenty-four criteria are tier M. The single tier A criterion is the sample-size plan artefact, and it
still asserts on JSON fields rather than prose, per Article XIII.

## Tranche exit condition

P1 is accepted when `bin/lab-verify-p1` reports every criterion PASS with per-tier totals printed separately, the two
new contracts are hash-frozen, the three P0 contracts are hash-verified unchanged, and `docs/p1-acceptance-memo.md`
records the measured cycle times and the sample-size plan.
