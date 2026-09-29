# SDD Tranche P11 — Answer-Grammar Re-Score of the Token-Scaling Runs

**Status:** proposed · forward experiment under the constitution in force (Articles I–XXI).
**Depends on:** P6/P6.1 (Arm B harness + the frozen answer extractor that is the instrument under repair), P9 (statlib `lib/lab_p9_statlib.py`), P10 (token-scaling sweep, banked completions in `results/scaling-runs-detail.jsonl`, frozen `results/scaling-runs.jsonl`).
**Read-only on:** all prior evidence, ledgers, representations, banked headlines, **and every P10 artefact including the banked model completions** (Article XVI). P11 adds a sidecar; it re-runs no scaling cell and changes no P10 number.

## One-paragraph purpose

P10 answered the scaling question in the feasibility sense: at 500k–1M tokens the raw-evidence prompt (R0) is physically un-submittable while the compact representation (R2) stays small (H2 HOLDS, 30/30 vs 30/30), and no recovery ever retained damage (H3 HOLDS). But P10's within-window accuracy hypothesis (H1) came back **NOT EVALUABLE**: the frozen P6.1 extractor rejected every within-window R0 answer as `refusal_parser` because the models named the right event with several locators (`lsn=X ts=T`, or one LSN in both hex and integer) that did not all resolve to *exactly* one LSN. The only evidence that R0 works at small scale is P10's **exploratory, non-binding** re-scoring. P11 repairs that one instrument defect under pre-registration: it freezes a principled, answer-blind, relaxed answer grammar BEFORE touching data, re-parses the banked P10 completions with it (no new model calls in the core path), re-scores via the unchanged P4 oracle, and evaluates — as pre-registered results — whether raw data works at small scale (H4) and whether R0 accuracy degrades within the window (H1-R).

## The claim P11 is built to test honestly

The goal is to show: **at small scale the raw row data works; at large scale it does not, and that is where the abstraction helps.** After P10:
- "large scale → R0 does not work → R2 helps" is **already proven** as feasibility (H2). P11 does not touch it.
- "small scale → R0 works" is **only exploratory**. P11 exists to make it a pre-registered result (H4).
- Pre-registered expectation, stated so it cannot be reverse-fitted: the exploratory data suggests R0 does **not** lose accuracy inside the window (Gemma 5/5, Qwen 5/5 at both anchor and S*). So H1-R (accuracy degradation) will most likely be a **null**, and the honest story stays *feasibility, not precision*. P11 must report that if it holds, not chase an accuracy cliff.

## What it is NOT

- Not a re-run of the scaling sweep. The infeasible 500k/1M cells are unchanged and unre-parsed (no completion exists to parse).
- Not a knob turned until R0 passes. The new grammar is a rule justified as an instrument fix, applied **symmetrically to R0 and R2**, frozen before any data.
- Not answer-aware. The extractor resolves locators using only the evidence/view, never the oracle optimum.

## Task order

`R001 → R007`, one task per invocation. R004 is **conditional** (fires only if R003 leaves H1-R/H4 underpowered per a pre-registered trigger). R005 needs R003 (and R004 if it fired); R006 needs R005; R007 last.
