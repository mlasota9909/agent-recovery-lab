# Checklist — P5.1: Model-View Separation

The agent fills `Date` and `Bundle` when a task completes. **The operator owns the `Reviewed` column** — the agent
never ticks it.

| Task | Title | Date | Bundle | Reviewed |
| --- | --- | --- | --- | --- |
| G001 | Article XVII; ADR-P5.1-1/2/3 | 2026-08-25 | logs/review/G001 | ☐ |
| G002 | Amendment-1; `lab-repr-modelview`/`-reference`; `lab-modelview-guard` | 2026-08-25 | logs/review/G002 | ☐ |
| G003 | Parity on model_view; PB-6 relabel; re-derive `lab-verify-p5`; artefacts byte-identical | 2026-08-25 | logs/review/G003 | ☐ |
| G004 | `bin/lab-verify-p5.1` gate; criterion mapping; memo | 2026-08-25 | logs/review/G004 | ☐ |

## Operator review order

1. `RESULT` line of the agent's report.
2. `logs/review/<task>/acceptance.md` — **check the tier column**, not just PASS.
3. The negative-test evidence. Confirm the check went red, then green again after revert.
4. `observations.md` — deviations and out-of-scope findings.
5. Hand spot-check two artefacts:
   - For G002, emit a `model_view` yourself (`bin/lab-repr-modelview <incident> R2 PB-6-candidate-windows '{"top_n":3}'`)
     and confirm by eye it has no `answer` and no `candidates`; then inject an `answer` and confirm
     `bin/lab-modelview-guard` refuses it.
   - For G003, confirm the R2 representation artefact hash equals its P5 (F004) hash, and that the headline now reports
     the PB-6 evidence-bytes delta with R2 strictly and materially below R0.

## Acceptance criteria coverage

| AC | Tier | Owning task |
| --- | --- | --- |
| AC-P5.1-01 | M | G001 |
| AC-P5.1-02 | M | G001 |
| AC-P5.1-03 | M | G002 |
| AC-P5.1-04 | M | G002 |
| AC-P5.1-05 | M | G002 |
| AC-P5.1-06 | M | G002 |
| AC-P5.1-07 | M | G002 |
| AC-P5.1-08 | M | G002 |
| AC-P5.1-09 | M | G003 |
| AC-P5.1-10 | M | G003 |
| AC-P5.1-11 | M | G003 |
| AC-P5.1-12 | M | G003 |
| AC-P5.1-13 | M | G004 |
| AC-P5.1-14 | M | G003 |
| AC-P5.1-15 | M | G004 |
| AC-P5.1-16 | A | G004 |

Fifteen of sixteen criteria are tier M. The single tier A criterion is the memo update, which asserts on
machine-readable fields, per Article XIII.

## Tranche exit condition

P5.1 is accepted when `bin/lab-verify-p5.1` reports every criterion PASS with per-tier totals printed separately,
Article XVII is in force, `model_view` and `reference` are split by amendment with the original contract byte-identical,
`bin/lab-repr-modelview` emits only the subject-visible surface and every emission passes `bin/lab-modelview-guard`,
the guard demonstrably refuses an injected answer and an injected provenance token, parity holds on the model_view
surface, the headline reports the PB-6 delta with R2 strictly and materially < R0, the R0/R1/R2 artefacts are
byte-identical to their P5 close, all frozen contract files are unchanged, and the old→new criterion mapping shows no
criterion was weakened.

## Note for P6

P6 (Arm B model harness) may proceed once P5.1 is accepted. **P6 MUST hand the model only the `model_view` object from
`bin/lab-repr-modelview`, and MUST pass every model input through `bin/lab-modelview-guard` before the model sees it**
(Article XVII). The `reference` answer is available via `bin/lab-repr-reference` for scoring-adjacent parity checks
only; it is never part of the model input. P6 scores the model's coordinate through the P4 restore+validate path
against the oracle, exactly as P3's Arm A is scored, so the two arms remain comparable.
