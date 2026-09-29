# Checklist — P3.1: Gate Integrity

The agent fills `Date` and `Bundle` when a task completes. **The operator owns the `Reviewed` column** — the agent
never ticks it.

| Task | Title | Date | Bundle | Reviewed |
| --- | --- | --- | --- | --- |
| Z001 | Article XVI; ADR-P3.1-1/2/3 | 2026-08-24 | logs/review/Z001/ | ☐ |
| Z002 | Read-only enforcement; remove the two write paths | 2026-08-24 | logs/review/Z002/ | ☐ |
| Z003 | Pinned fixtures; `bin/lab-regression`; re-derive `lab-verify-p3` | 2026-08-24 | logs/review/Z003/ | ☐ |
| Z004 | `bin/lab-verify-p3.1` gate; criterion mapping; memo | 2026-08-24 | logs/review/Z004/ | ☐ |

## Operator review order

1. `RESULT` line of the agent's report.
2. `logs/review/<task>/acceptance.md` — **check the tier column**, not just PASS.
3. The negative-test evidence. Confirm the check went red, then green again after revert.
4. `observations.md` — deviations and out-of-scope findings.
5. Hand spot-check two artefacts:
   - For Z002, run one gate under `bin/lab-gate-readonly-check` yourself and confirm the evidence manifest is identical
     before and after.
   - For Z003, open one fixture under `fixtures/regression/` and confirm it is a real captured incident (has a
     `db.jsonl` that reconciles clean), not a stub, and that `bin/lab-regression` runs its gate green against it.

## Acceptance criteria coverage

| AC | Tier | Owning task |
| --- | --- | --- |
| AC-P3.1-01 | M | Z001 |
| AC-P3.1-02 | M | Z001 |
| AC-P3.1-03 | M | Z002 |
| AC-P3.1-04 | M | Z002 |
| AC-P3.1-05 | M | Z002 |
| AC-P3.1-06 | M | Z002 |
| AC-P3.1-07 | M | Z003 |
| AC-P3.1-08 | M | Z003 |
| AC-P3.1-09 | M | Z003 |
| AC-P3.1-10 | M | Z003 |
| AC-P3.1-11 | M | Z003 |
| AC-P3.1-12 | M | Z004 |
| AC-P3.1-13 | M | Z004 |
| AC-P3.1-14 | M | Z004 |
| AC-P3.1-15 | M | Z003 |
| AC-P3.1-16 | A | Z004 |

Fifteen of sixteen criteria are tier M. The single tier A criterion is the memo update, which asserts on
machine-readable fields, per Article XIII.

## Tranche exit condition

P3.1 is accepted when `bin/lab-verify-p3.1` reports every criterion PASS with per-tier totals printed separately,
Article XVI is in force, every `bin/lab-verify*` passes `bin/lab-gate-readonly-check` (evidence byte-identical before
and after), the two known write paths are removed, a real pinned regression fixture exists per prior tranche,
`bin/lab-regression` is green across all prior gates and demonstrably able to go red, `bin/lab-verify-p3` is
re-derived to an honest green, the SC-01 headline is byte-identical to its P3 close, all frozen contract hashes are
unchanged, and the old→new criterion mapping shows no criterion was weakened.

## Note for P4

P4 (restore + validation) may proceed once P3.1 is accepted: the regression signal it relies on to know the prior
instruments are intact is now both meaningful (runs against real fixtures) and achievable (does not require a frozen
incident to be in a live state). P4 must still refuse any arm coordinate whose `selection_inputs` peek flags are not
all `false`, and Article XVI now binds P4's own validation checks — they read evidence and write only under
`logs/review/`.
