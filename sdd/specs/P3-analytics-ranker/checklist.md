# Checklist — P3: Derived Analytics & the Arm A Deterministic Ranker

The agent fills `Date` and `Bundle` when a task completes. **The operator owns the `Reviewed` column** — the agent
never ticks it.

| Task | Title | Date | Bundle | Reviewed |
| --- | --- | --- | --- | --- |
| D001 | Freeze both P3 contracts; record entry gate | 2026-08-24 | logs/review/D001/ | ☐ |
| D002 | SC-01 injector + workload + oracle params → reconciled incident | 2026-08-24 | logs/review/D002/ | ☐ |
| D003 | `bin/lab-analytics` (burst/churn/deletion/DDL flag) | 2026-08-24 | logs/review/D003/ | ☐ |
| D004 | mean+3σ anomaly scoring vs declared baseline | 2026-08-24 | logs/review/D004/ | ☐ |
| D005 | `bin/lab-candidates` candidate generation | 2026-08-24 | logs/review/D005/ | ☐ |
| D006 | `bin/lab-rank` Arm A deterministic ranker | 2026-08-24 | logs/review/D006/ | ☐ |
| D007 | `bin/lab-naive` naive comparator | 2026-08-24 | logs/review/D007/ | ☐ |
| D008 | Wire both arms into `evaluate-arm` | 2026-08-24 | logs/review/D008/ | ☐ |
| D009 | Headline SC-01 + provenance/no-peek negatives | 2026-08-24 | logs/review/D009/ | ☐ |
| D010 | `bin/lab-verify-p3` gate; contracts re-verified; handoff | 2026-08-24 | logs/review/D010/ | ☐ |

## Operator review order

1. `RESULT` line of the agent's report.
2. `logs/review/<task>/acceptance.md` — **check the tier column**, not just PASS.
3. The negative-test evidence. Confirm the check went red, then green again after revert.
4. `observations.md` — deviations and out-of-scope findings.
5. Hand spot-check two artefacts. For **D002**, confirm the SC-01 incident reconciles exactly-once (0 gaps, 0 dupes)
   and the injection log's damage window is real. For **D009**, read Arm A and naive recovery-point errors straight
   from the results row and confirm Arm A won; then **personally re-run the strip-provenance test** and confirm Arm
   A's chosen coordinate is byte-identical with and without provenance.

## Acceptance criteria coverage

| AC | Tier | Owning task |
| --- | --- | --- |
| AC-P3-01 | M | D001 |
| AC-P3-02 | M | D002 |
| AC-P3-03 | M | D002 |
| AC-P3-04 | M | D003 |
| AC-P3-05 | M | D003 |
| AC-P3-06 | M | D004 |
| AC-P3-07 | M | D004 |
| AC-P3-08 | M | D005 |
| AC-P3-09 | M | D005 |
| AC-P3-10 | M | D006 |
| AC-P3-11 | M | D006 |
| AC-P3-12 | M | D007 |
| AC-P3-13 | M | D008 |
| AC-P3-14 | M | D009 |
| AC-P3-15 | M | D009 |
| AC-P3-16 | M | D009 |
| AC-P3-17 | M | D010 |
| AC-P3-18 | M | D010 |
| AC-P3-19 | A | D010 |

Eighteen of nineteen criteria are tier M. The single tier A criterion is the handoff record, which asserts on
machine-readable fields, per Article XIII.

## Tranche exit condition

P3 is accepted when `bin/lab-verify-p3` reports every criterion PASS with per-tier totals printed separately; both P3
contracts are frozen and hash-verified; SC-01 is realized as a reconciled incident; analytics and anomaly scoring are
deterministic and provenance-blind; candidates and the Arm A coordinate conform to the frozen schemas; the naive
comparator's time error is declared and fixed; both arms' recovery-point errors auto-land in the results row; Arm A
beats naive on SC-01 honestly; the strip-provenance and no-peek negative tests pass; and all prior gates and contract
hashes (through P2.1) are unchanged.

## Note for P4 and P5

- **P4** (restore + validation) consumes the `arm-coordinate` record: it restores against the chosen coordinate and
  validates the restored state against the oracle. Do not begin P4 against an arm coordinate that failed its
  `selection_inputs` no-peek check.
- **P5** (representations R0/R1/R2) and **P6** (Arm B) are measured against the Arm A number this tranche produces.
  P5 reads the same provenance-blind ledger and must obey the same Article II rule (§5 of `capture-completeness.md`).
