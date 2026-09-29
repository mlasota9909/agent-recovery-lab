# Checklist — P2.1: Reconciliation Soundness & Contract Amendment

The agent fills `Date` and `Bundle` when a task completes. **The operator owns the `Reviewed` column** — the agent
never ticks it.

| Task | Title | Date | Bundle | Reviewed |
| --- | --- | --- | --- | --- |
| Y001 | Article XV; ADR-P2.1-1 deviation record | 2026-08-24 | `logs/review/Y001/` | ☐ |
| Y002 | `xid` recovered; greedy fallback withdrawn; amendment-1 frozen | 2026-08-24 | `logs/review/Y002/` | ☐ |
| Y003 | Repeated-key reconciliation soundness test | 2026-08-24 | `logs/review/Y003/` | ☐ |
| Y004 | `bin/lab-verify-p2.1` gate; contracts re-verified; memo | 2026-08-24 | `logs/review/Y004/` | ☐ |

## Operator review order

1. `RESULT` line of the agent's report.
2. `logs/review/<task>/acceptance.md` — **check the tier column**, not just PASS.
3. The negative-test evidence. Confirm the check went red, then green again after revert.
4. `observations.md` — deviations and out-of-scope findings.
5. Hand spot-check two artefacts. For Y002, hand-trace one repeated-key incident: pick a natural key touched twice,
   find both workload ops and both ledger records, and confirm the `xid`-keyed mapping pairs them correctly.

## Acceptance criteria coverage

| AC | Tier | Owning task |
| --- | --- | --- |
| AC-P2.1-01 | M | Y001 |
| AC-P2.1-02 | M | Y002 |
| AC-P2.1-03 | M | Y002 |
| AC-P2.1-04 | M | Y001 |
| AC-P2.1-05 | M | Y002 |
| AC-P2.1-06 | M | Y002 |
| AC-P2.1-07 | M | Y002 |
| AC-P2.1-08 | M | Y002 |
| AC-P2.1-09 | M | Y002 |
| AC-P2.1-10 | M | Y003 |
| AC-P2.1-11 | M | Y003 |
| AC-P2.1-12 | M | Y003 |
| AC-P2.1-13 | M | Y002 |
| AC-P2.1-14 | M | Y004 |
| AC-P2.1-15 | M | Y004 |
| AC-P2.1-16 | A | Y004 |

Fifteen of sixteen criteria are tier M. The single tier A criterion is the memo update, which asserts on
machine-readable fields, per Article XIII.

## Tranche exit condition

P2.1 is accepted when `bin/lab-verify-p2.1` reports every criterion PASS with per-tier totals printed separately,
Article XV is in force, `capture-completeness.md` is byte-identical and re-verifies, `capture-completeness.amendment-1.md`
is frozen, `xid` is recovered and cross-validated on both ledger sides, `bin/lab-ledger-account` maps by the
`xid`-bearing key with no greedy fallback, the repeated-key soundness test detects a masked corruption and passes
clean after revert, `bin/lab-verify-p2` is still 18/18, and the P0/P1/P2 contract hashes are verified unchanged.

## Note for P3

P3 (derived analytics + Arm A ranker) may consume scenario ledgers only after P2.1 is accepted: the reconciliation
that certifies a ledger complete is proven sound under repeated keys as of Y003. P3 inherits the amended key —
`capture-completeness.md` read together with `capture-completeness.amendment-1.md` — and Article II still forbids any
analytics or ranking path from reading `principal`.
