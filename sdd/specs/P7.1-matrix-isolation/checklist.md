# Checklist — P7.1: Matrix Isolation

The agent fills `Date` and `Bundle` when a task completes. **The operator owns the `Reviewed` column** — the agent
never ticks it.

| Task | Title | Date | Bundle | Reviewed |
| --- | --- | --- | --- | --- |
| L001 | Article XIX; D1 root cause; FULL/FALLBACK decision | 2026-08-27 | `logs/review/L001/` | ☐ |
| L002 | `incident-isolation.md`; per-incident isolation; sibling-safety test | 2026-08-27 | `logs/review/L002/` | ☐ |
| L003 | SC-02 oracle manifest + P4; SC-03/04 set-validation | 2026-08-27 | `logs/review/L003/` | ☐ |
| L004 | live re-run under isolation; supersede; validity partition | 2026-08-28 | `logs/review/L004/` | ☐ |
| L005 | disaggregated honest headline | 2026-08-28 | `logs/review/L005/` | ☐ |
| L006 | `bin/lab-verify-p7.1` gate; mapping; memo | 2026-08-28 | `logs/review/L006/` | ☐ |

## Operator review order

1. `RESULT` line of the agent's report.
2. `logs/review/<task>/acceptance.md` — **check the tier column**, not just PASS.
3. The negative-test evidence. Confirm the check went red, then green again after revert.
4. `observations.md` — deviations and out-of-scope findings.
5. Hand spot-check:
   - For **L001**, read `decision.json`; countersign FULL or FALLBACK yourself before L002 runs. This is the timeline
     guard — do not let it default.
   - For **L002**, create two incidents yourself, reset one, and confirm the other's snapshot list and heartbeat
     digest are byte-identical; then attempt `zfs rollback -r labpool/victim@…` and confirm `bin/lab-reset` refuses.
   - For **L003**, confirm SC-02 scores a real P4 verdict (not `stub`) and SC-03/04 record precision/recall + an
     earliest-safe bound.
   - For **L004**, read `matrix-completeness.json`: confirm the validity partition is present, no `run_failure` is
     undiagnosed, and every superseded cell retains a pointer. Confirm re-run cells show `resolved_by: live_heartbeat`
     with a non-zero `skew_ms`.
   - For **L005**, open `headline.json`: confirm actionability and compactness are separate fields, SC-04's
     `compactness_holds:false` is present, and SC-01 is the sole P4-validated headline.

## Acceptance criteria coverage

| AC | Tier | Owning task |
| --- | --- | --- |
| AC-P7.1-01 | M | L001 |
| AC-P7.1-02 | M | L001 |
| AC-P7.1-03 | A | L001 |
| AC-P7.1-04 | M | L002 |
| AC-P7.1-05 | M | L002 |
| AC-P7.1-06 | M | L002 |
| AC-P7.1-07 | M | L002 |
| AC-P7.1-08 | M | L003 |
| AC-P7.1-09 | M | L003 |
| AC-P7.1-10 | M | L004 |
| AC-P7.1-11 | M | L004 |
| AC-P7.1-12 | M | L004 |
| AC-P7.1-13 | M | L004 |
| AC-P7.1-14 | M | L005 |
| AC-P7.1-15 | M | L005 |
| AC-P7.1-16 | M | L005 |
| AC-P7.1-17 | M | L004 |
| AC-P7.1-18 | M | L006 |
| AC-P7.1-19 | M | L004 |
| AC-P7.1-20 | M | L006 |
| AC-P7.1-21 | A | L006 |

Nineteen of twenty-one criteria are tier M. The two tier A criteria are the L001 decision record and the L006 memo,
both asserting on machine-readable fields, per Article XIII.

## Tranche exit condition

P7.1 is accepted when `bin/lab-verify-p7.1` reports every criterion PASS with per-tier totals printed separately,
Article XIX is in force, the shared-pool root cause is fixed by per-incident isolation with the invariant proven (FULL)
or documented as the bounding limitation (FALLBACK), the new scenarios are ground-truth validated or explicitly
bounded, completeness is reported with a validity partition, prior failed cells are superseded not deleted, the SC-04
headline is disaggregated, the SC-01 banked headline is byte-identical, all frozen contract files are unchanged, and
the old->new criterion mapping shows no criterion was weakened.

## Note for P8

P8 (analysis) may proceed once P7.1 is accepted. It consumes `results/matrix.jsonl` with the
validity partition and the L005 disaggregated headline, reports completeness only alongside validity, and carries the
actionability/compactness disaggregation into the reported results. It does not re-open the model pin, the representations, or the
SC-01 headline.
