# Checklist — P6: Arm B, the modest-local-model harness

The agent fills `Date` and `Bundle` when a task completes. **The operator owns the `Reviewed` column** — the agent
never ticks it.

| Task | Title | Date | Bundle | Reviewed |
| --- | --- | --- | --- | --- |
| H001 | Freeze P6 contracts; pin model; record entry gate | 2026-08-26 | logs/review/H001/ | [ ] |
| H002 | `bin/lab-model` offline pinned invocation | 2026-08-26 | logs/review/H002/ | [ ] |
| H003 | `bin/lab-arm-b-prompt` single guarded choke point | 2026-08-26 | logs/review/H003/ | [ ] |
| H004 | `bin/lab-arm-b-extract` deterministic extraction + refusal | 2026-08-26 | logs/review/H004/ | [ ] |
| H005 | `bin/lab-arm-b` refusal-aware run driver, K replicates | 2026-08-26 | logs/review/H005/ | [ ] |
| H006 | verbatim provenance-blind rationale capture | 2026-08-26 | logs/review/H006/ | [ ] |
| H007 | real token + latency telemetry to results row | 2026-08-26 | logs/review/H007/ | [ ] |
| H008 | scoring through unchanged P4; emit frozen arm-coordinate | 2026-08-26 | logs/review/H008/ | [ ] |
| H009 | SC-01 headline R0/R1/R2 + discrimination negatives | 2026-08-26 | logs/review/H009/ | [ ] |
| H010 | `bin/lab-verify-p6` gate; hashes re-verified; handoff | 2026-08-26 | logs/review/H010/ | [ ] |

## Operator review order

1. `RESULT` line, `HARNESS DETERMINISTIC`, `MODEL PINNED + OFFLINE` and `PROVENANCE-BLIND` lines of the agent's report.
2. `logs/review/<task>/acceptance.md` — **check the tier column**, not just PASS.
3. The negative-test evidence. Confirm the check went red, then green again after revert.
4. `observations.md` — deviations and out-of-scope findings.
5. Hand spot-check. For **H003**, try to find a second path that reaches the model, and confirm an injected `answer` is
   refused by the guard. For **H004/H005**, confirm a "cannot determine" completion is recorded as a refusal, not a
   guess. For **H008/H012-behaviour**, re-run extraction+scoring over a recorded completion and confirm byte-identical
   output. For **H009**, confirm the R0/R1/R2 coordinate errors are computed against ground truth from machine-readable
   fields, and that the guard-bypass / coerced-refusal / injected-principal negatives are each caught.

## Acceptance criteria coverage

| AC | Tier | Owning task |
| --- | --- | --- |
| AC-P6-01 | M | H001 |
| AC-P6-02 | M | H002 |
| AC-P6-03 | M | H003 |
| AC-P6-04 | M | H003 |
| AC-P6-05 | M | H003 |
| AC-P6-06 | M | H004 |
| AC-P6-07 | M | H004 |
| AC-P6-08 | M | H006 |
| AC-P6-09 | M | H007 |
| AC-P6-10 | M | H008 |
| AC-P6-11 | M | H008 |
| AC-P6-12 | M | H008 |
| AC-P6-13 | A | H005, H009 |
| AC-P6-14 | M | H009 |
| AC-P6-15 | M | H009 |
| AC-P6-16 | M | H008 |
| AC-P6-17 | M | H010 |
| AC-P6-18 | M | H010 |
| AC-P6-19 | A | H010 |

Seventeen of nineteen criteria are tier M. The two tier A criteria (replicate characterisation, handoff record) assert
on machine-readable fields, per Article XIII.

## Tranche exit condition

P6 is accepted when `bin/lab-verify-p6` reports every criterion PASS with per-tier totals printed separately and is
itself proven read-only over the evidence root; both P6 contracts are frozen and hash-verified; the offline model is
pinned (greedy + seed + weights hash) and provably offline; there is a single guarded prompt-assembly choke point with
no bypass; extraction is deterministic with a first-class refusal path that is never coerced; the rationale is captured
verbatim and provenance-blind; real token/latency telemetry is recorded distinct from P5's estimate; every
determination is scored through the unchanged P4 path into the frozen arm-coordinate shape with `read_*` all false; the
SC-01 headline runs the same model over R0/R1/R2 with objective error vs ground truth appended automatically and the
R0-vs-R1-vs-R2 table produced from machine-readable fields; the discrimination negatives prove guard, refusal and
blindness are enforced; all prior gates, regression and contract hashes (through P5.1) are unchanged; and the P6
handoff is written without anti-goal inversion.

## Note for P7 and P8

- **P7** (run matrix) drives Arm B (and Arm A/naive) across SC-01..SC-04 and the timing patterns, appending one
  results row per run unattended. It reuses `bin/lab-arm-b` unchanged; it does not fork the harness or re-pin the model.
- **P8** (analysis) reports the R0-vs-R1-vs-R2 comparison and the Arm A vs Arm B contrast from the results file, and
  draws the model's verbatim explanations for the operator-assistance argument. P6 establishes the result on SC-01;
  P7 scales it and SC-04 is where the R0-vs-R2 gap should be largest.
