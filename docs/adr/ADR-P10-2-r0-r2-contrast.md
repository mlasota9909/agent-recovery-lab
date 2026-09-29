# ADR-P10-2 — R0 and R2 are the contrast; R1 is not run in P10

Status: accepted 2026-09-24 (P10 Q001; transcribed from `sdd/specs/P10-token-scaling/plan.md`)
Authority: P10 plan; fixed before data by `scaling-analysis-plan.amendment-1.md` P7.

## Context

P9 found that R1 (time-window aggregates) was dominated and confusing. The plan made R1
optional: "only if throughput allows".

## Decision

The primary sweep is R0 (the raw change log) versus R2 (the graph with summaries). The
plan left R1's inclusion to throughput, which would be decided after seeing the sweep. To
remove that post-hoc choice, Q001 fixes it before data: R1 is not run in P10.

## Consequences

The omission is deliberate and recorded, not silent. R1 conclusions stay those of P9.
