# ADR-P10-4 — Canonical tokens size the sweep; model tokens and real windows decide feasibility

Status: accepted 2026-09-24 (P10 Q001; transcribed from `sdd/specs/P10-token-scaling/plan.md`)
Authority: P10 plan; refined by `scaling-analysis-plan.amendment-1.md` P1–P3 (ADR-P10-8).

## Context

The three models use different tokenizers, so a single model-independent x-axis is needed.

## Decision

- Scale targets are set in the pinned canonical tokenizer (`lab-ws-punct-1`), so the
  x-axis is the same for every model.
- For each cell, feasibility is decided by the model's own token count against its real
  window.
- Both counts are stored.

The window figure first written here (262 144 for all models) is corrected per model in
ADR-P10-8.
