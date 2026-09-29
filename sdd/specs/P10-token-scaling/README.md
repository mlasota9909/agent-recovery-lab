# SDD Tranche P10 — Token-Scaling of the Recovery-Point Task

**Status:** proposed · forward experiment under the constitution in force (Articles I–XXI).
**Depends on:** P1 (results-row + oracle), P3 (Arm A ranker + naive), P5/P5.1 (representations + model_view guard), P6/P6.1 (Arm B model harness + answerable grammar), P9 (multi-model sweep + pre-registered statistics harness `lib/lab_p9_statlib.py`).
**Read-only on:** all prior evidence, ledgers, frozen results rows, representations, and banked headlines (Article XVI).

## One-paragraph purpose

P9 showed the representation effect is real but model-specific on the SC-01 incident **at its natural size** (R0 ≈ 44 KB / ~17.9 k tokens, well inside every model's 262 144-token window). That leaves an obvious question unanswered: *if the raw log already fits, why does a compact representation matter?* P10 answers it by holding the SC-01 incident and its true recovery point fixed and **synthetically scaling the legitimate change history** so the raw-evidence representation (R0) is driven from ~10 k tokens up through and beyond the model context window (10 k → 1 M), while the compact representation (R2) grows only with the number of summary windows. It measures, under a pre-registered plan, where R0 acceptance and recovery accuracy fall off and where R0 becomes physically un-submittable, versus R2.

## What it is NOT

- It is **not** a claim that R2 is universally better. P9 stands: the effect is model-specific and compression costs recovery precision. P10 characterises **where scale forces the trade-off**, nothing more.
- It is **not** a real large-incident field test. The scaling is synthetic padding of legitimate activity, and that is a stated limitation.
- It changes **no** P9 number and re-runs **no** prior tranche.

## Task order

`Q001 → Q007`, one task per invocation. Q002/Q003 independent after Q001; Q005 needs Q004; Q006 needs Q005.
