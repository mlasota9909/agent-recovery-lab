# P11 — Plan and Architecture Decisions

## Approach

Re-analysis first, re-run only if forced. The core path re-parses banked completions and re-scores them; no model is called unless the pre-registered under-power trigger fires. Everything except the extractor is reused unchanged: the P4 oracle/restore-validate, the P9 statlib, the P10 feasibility rows (inherited read-only), the containment path (only if R004 fires).

## ADRs

- **ADR-P11-1 (instrument repair, not a knob).** The grammar is specified by a resolution rule and frozen before data. Justification: P10 diagnosed a genuine extractor defect (right event, multi-locator, rejected). Consequence: the grammar is applied symmetrically to R0 and R2 and is answer-blind; both are gated with negative tests so the repair cannot be mistaken for outcome-tuning.
- **ADR-P11-2 (re-parse the full submitted set).** Not just the 33 parser-refusals. The new grammar can change an already-accepted or an R2 parse; re-parsing everything and running the consistency gate is the only way to prove the change is scoped to the defect and nothing else moved.
- **ADR-P11-3 (extraction changes; scoring does not).** The unchanged P4 oracle scores whatever coordinate is extracted. This isolates the variable to the instrument and keeps every verdict comparable to P10.
- **ADR-P11-4 (re-run is conditional and cheap-by-default).** Model calls are the expensive, higher-risk path. R004 fires only on a mechanical under-power trigger (any H4/H1-R cell < 5 evaluable replicates after re-parse) and is otherwise skipped by rule. This directly honours the operator's "only if it actually helps".
- **ADR-P11-5 (report-whatever-it-shows, pre-registered).** All three H4/H1-R branches have verbatim interpretations frozen before data. The H4 ∧ ¬H1-R branch (small-scale works, no within-window degradation) is the *expected* and *good* result and must not be treated as a disappointment or nudged toward an accuracy cliff.

## Sizing

The core re-parse is CPU-only over ~155 banked completions (P10 submitted set: 87 accepted + 33 parser-refusal + 35 genuine-refusal). Minutes, not hours. R004, if it fires, tops up only the specific under-powered within-window R0 cells to 5 replicates — a handful of contained calls at most, never the infeasible cells.

## No new constitutional article

P11 is a forward experiment under Articles I–XXI. If review finds a class the gates miss (e.g. an extraction-time leak), that becomes Article XXII. The R007 handoff carries the anti-inversion guard: the only downstream consumer is human review of the outputs; do not copy an anti-goal forward.
