# P10 — Plan and Architecture Decisions

## Approach

Reuse the entire proven harness. The only new code is the scale generator and the scaling analysis; everything else (capture reconciliation P2/P2.1, oracle + restore-validate P4, representations + guard P5/P5.1, model harness P6/P6.1, statlib P9) is called unchanged.

## ADRs

- **ADR-P10-1 (padding is legitimate-only, placement is onset-blind).** The generator pads with legitimate activity whose placement depends only on `(seed, scale_target)`, never on the injection log or oracle. This keeps the true optimum fixed and prevents onset leakage. Consequence: the malicious window's *relative* position drifts as padding grows — recorded per run so "lost in the middle" can be read against it.
- **ADR-P10-2 (R0 and R2 are the contrast; R1 optional).** P9 showed R1 (time-window aggregates) is dominated and confusing. To conserve runway, the primary sweep is R0 vs R2; R1 is run only if throughput allows and is reported as secondary. Rationale recorded so the omission is deliberate, not silent.
- **ADR-P10-3 (`infeasible_context` is a result, not a failure).** When the assembled prompt exceeds a model's window the cell is `infeasible_context` and contributes to feasibility metrics. This is the hard-limit finding; treating it as a failure would hide the point.
- **ADR-P10-4 (canonical tokens size the sweep; model tokens are recorded).** Targets are set in one pinned canonical tokenizer so the x-axis is model-independent; each model's real `prompt_tokens` and its 262 144 window decide feasibility per cell. Both are stored.
- **ADR-P10-5 (report-whatever-it-shows, pre-registered).** All four branches of A4 have verbatim interpretations frozen before data. The ¬H1∧H2 branch (feasibility-not-accuracy) is explicitly a *good* result and must not be treated as a disappointment.

## Sizing (Q001 output)

Re-measure per-cell cost (assemble + submit + score + reset) on one 200k R0 cell before committing K. Default K=5 to match P9; drop to K=3 for the 500k/1M cells if throughput demands, recorded per cell. Total default sweep = 2 reps-set × 7 targets × 3 models × K. `infeasible_context` cells cost ~0 (no submission) so the tail is cheap.

## No new constitutional article

P10 is a forward experiment under Articles I–XXI. If the review finds a class the gates miss (e.g. a scaling-specific leak), that becomes Article XXII. The Q007 handoff carries the anti-inversion guard: it states the only downstream consumer is human review of the outputs, and must not copy an anti-goal forward.
