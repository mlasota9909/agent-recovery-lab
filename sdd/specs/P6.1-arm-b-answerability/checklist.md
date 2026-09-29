# Checklist — P6.1: Arm B Answerability

The agent fills `Date` and `Bundle` when a task completes. **The operator owns the `Reviewed` column** — the agent
never ticks it.

| Task | Title | Date | Bundle | Reviewed |
| --- | --- | --- | --- | --- |
| J001 | Article XVIII; refusal diagnosis; ADR-P6.1-1..4 | 2026-08-26 | logs/review/J001/ | ☐ |
| J002 | `model-runtime.amendment-1`; containment check rewrite | 2026-08-26 | logs/review/J002/ | ☐ |
| J003 | `arm-b-protocol.amendment-1`; prompt + extractor rebuild | 2026-08-26 | logs/review/J003/ | ☐ |
| J004 | SC-01 Arm B re-run; honest headline; null quarantined | 2026-08-26 | logs/review/J004/ | ☐ |
| J005 | `bin/lab-verify-p6.1` gate; criterion mapping; memo | 2026-08-26 | logs/review/J005/ | ☐ |

## Operator review order

1. `RESULT` line of the agent's report.
2. `logs/review/<task>/acceptance.md` — **check the tier column**, not just PASS.
3. The negative-test evidence. Confirm the check went red, then green again after revert.
4. `observations.md` — deviations and out-of-scope findings.
5. Hand spot-check:
   - For J001, open two of the 15 raw completions in `logs/review/H009/` yourself and confirm the classification in
     `refusal-diagnosis.json` matches what the model actually wrote. This is the task the whole tranche turns on.
   - For J002, run the containment check against the pinned endpoint and confirm `containment_verified:true` with the
     sub-checks named; then point it at a public address and confirm it refuses.
   - For J003, emit a `model_view`, assemble a prompt, and confirm the broadened grammar still passes the guard and
     still refuses a spliced `answer`; confirm the prompt is byte-identical across R0/R1/R2 except `content`.
   - For J004, read the new `headline.json`; if any arm still refuses, confirm the refusal carries its J001-taxonomy
     cause and is not silently dropped.

## Acceptance criteria coverage

| AC | Tier | Owning task |
| --- | --- | --- |
| AC-P6.1-01 | M | J001 |
| AC-P6.1-02 | M | J001 |
| AC-P6.1-03 | M | J001 |
| AC-P6.1-04 | M | J002 |
| AC-P6.1-05 | M | J002 |
| AC-P6.1-06 | M | J002 |
| AC-P6.1-07 | M | J003 |
| AC-P6.1-08 | M | J003 |
| AC-P6.1-09 | M | J003 |
| AC-P6.1-10 | M | J003 |
| AC-P6.1-11 | M | J003 |
| AC-P6.1-12 | M | J003 |
| AC-P6.1-13 | M | J004 |
| AC-P6.1-14 | M | J004 |
| AC-P6.1-15 | M | J003 |
| AC-P6.1-16 | M | J004 |
| AC-P6.1-17 | M | J005 |
| AC-P6.1-18 | M | J005 |
| AC-P6.1-19 | A | J005 |

Eighteen of nineteen criteria are tier M. The single tier A criterion is the memo update, which asserts on
machine-readable fields, per Article XIII.

## Tranche exit condition

P6.1 is accepted when `bin/lab-verify-p6.1` reports every criterion PASS with per-tier totals printed separately,
Article XVIII is in force, the null is diagnosed to per-completion causes, the containment contract and check are
corrected by amendment to the truth of the cross-host deployment with the original byte-identical, the answer grammar
is a resolvable locator and the task framing is relaxed (byte-identical across R0/R1/R2, refusal still first-class,
guard still binding), SC-01 Arm B is re-run with an honest headline and any residual refusal diagnosed, the R0/R1/R2
artefacts are byte-identical to their P5/P5.1 close, all frozen contract files are unchanged, and the old→new criterion
mapping shows no criterion was weakened.

## Note for P7

P7 (the run matrix) may proceed once P6.1 is accepted. P7 drives Arm A, naive and Arm B across SC-01..SC-04 and the
timing patterns, reusing `bin/lab-arm-b` unchanged. It MUST use the amended grammar and the corrected containment check,
MUST keep the single guarded assembly path (Article XVII), and MUST treat any refusal as first-class data carrying its
diagnosed cause (Article XVIII). It does not re-open the model pin or the representations.
