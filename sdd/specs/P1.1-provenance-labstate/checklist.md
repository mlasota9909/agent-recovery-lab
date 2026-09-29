# Checklist — P1.1: Provenance & Lab-State Remediation

The agent fills `Date` and `Bundle` when a task completes. **The operator owns the `Reviewed` column** — the agent
never ticks it.

| Task | Title | Date | Bundle | Reviewed |
| --- | --- | --- | --- | --- |
| X001 | Article XIV; false handoff note corrected | 2026-08-21 | `logs/review/X001/` | ☐ |
| X002 | `harness_commit` = HEAD at production; dirty-tree refusal | 2026-08-21 | `logs/review/X002/` | ☐ |
| X003 | P1 stub rows quarantined under `results/fixtures/` | 2026-08-21 | `logs/review/X003/` | ☐ |
| X004 | `bin/lab-ready` gate + tested recovery runbook | 2026-08-21 | `logs/review/X004/` | ☐ |
| X005 | Planned-vs-completed disambiguation | 2026-08-21 | `logs/review/X005/` | ☐ |
| X006 | `bin/lab-verify-p1.1` gate; contracts re-verified; memo | 2026-08-21 | `logs/review/X006/` | ☐ |

## Operator review order

1. `RESULT` line of the agent's report.
2. `logs/review/<task>/acceptance.md` — **check the tier column**, not just PASS.
3. The negative-test evidence. Confirm the check went red, then green again after revert.
4. `observations.md` — deviations and out-of-scope findings.
5. Hand spot-check two artefacts. For X002, hand-verify one results row's `harness_commit` against `git rev-parse
   HEAD` yourself.

## Acceptance criteria coverage

| AC | Tier | Owning task |
| --- | --- | --- |
| AC-P1.1-01 | M | X001 |
| AC-P1.1-02 | M | X001 |
| AC-P1.1-03 | M | X002 |
| AC-P1.1-04 | M | X002 |
| AC-P1.1-05 | M | X002 |
| AC-P1.1-06 | M | X002 |
| AC-P1.1-07 | M | X003 |
| AC-P1.1-08 | M | X003 |
| AC-P1.1-09 | M | X004 |
| AC-P1.1-10 | M | X004 |
| AC-P1.1-11 | M | X004 |
| AC-P1.1-12 | M | X005 |
| AC-P1.1-13 | M | X005 |
| AC-P1.1-14 | M | X006 |
| AC-P1.1-15 | M | X006 |
| AC-P1.1-16 | A | X006 |

Fifteen of sixteen criteria are tier M. The single tier A criterion is the memo update, which asserts on
machine-readable fields, per Article XIII.

## Tranche exit condition

P1.1 is accepted when `bin/lab-verify-p1.1` reports every criterion PASS with per-tier totals printed separately,
Article XIV is in force, `harness_commit` is HEAD-at-production with a dirty-tree refusal, the P1 stub rows are
quarantined, `bin/lab-ready` passes on a healthy lab and fails on an unhealthy one, planned-vs-completed is
disambiguated, and the P0/P1 contract hashes are verified unchanged.

## Note for P2

P2's entry condition is `bin/lab-ready` exit 0 (ADR-P1.1-4). Do not begin P2 capture work until it passes.
