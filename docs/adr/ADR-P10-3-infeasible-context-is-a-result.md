# ADR-P10-3 — `infeasible_context` is a result, not a failure

Status: accepted 2026-09-24 (P10 Q001; transcribed from `sdd/specs/P10-token-scaling/plan.md`)
Authority: P10 plan; operationalised by `scaling-analysis-plan.amendment-1.md` P3 (ADR-P10-8).

## Context

At large scales the assembled R0 prompt cannot be sent to a model with a finite window.

## Decision

When the prompt plus the frozen completion budget exceeds a model's window, the cell is
recorded as `infeasible_context`. It is not submitted, it counts toward feasibility
metrics, and it is never relabelled as a refusal or a run failure.

## Consequences

The hard-limit finding stays visible instead of being hidden as missing data.
