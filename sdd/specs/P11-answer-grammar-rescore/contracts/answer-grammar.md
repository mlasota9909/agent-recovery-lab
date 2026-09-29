# FROZEN CONTRACT — Relaxed Answer Grammar (P11)

Frozen at R001, BEFORE any completion is re-parsed. It repairs the P6.1 extractor defect diagnosed in P10 (multi-locator answers rejected even when they name one event). Superseding changes use an Article XV amendment; the original stays byte-identical. The grammar is an INSTRUMENT specified by a rule; it is never tuned to a target outcome.

## G1. What the extractor consumes and MUST NOT consume

- **Consumes:** the model completion text, and the frozen model-visible evidence/view for that cell (to resolve a locator to an LSN).
- **MUST NOT consume:** the oracle optimum, `injection_log.json`, the answer key, or any provenance/`principal` field. Extraction is **answer-blind** (Articles II, XVII). Enforced by R002's negative test.

## G2. Locator types recognised (superset of P6.1)

A model answer may offer one or more locators for its chosen recovery point:
- `lsn_int` — an LSN as an integer.
- `lsn_hex` — an LSN in PostgreSQL `X/Y` hex form.
- `ts` — a timestamp, resolved at the recorded heartbeat granularity (~1 s) to the unique commit LSN whose commit time falls in that heartbeat window in the evidence.
- `event_ref` — a reference to a named change record visible in the view (e.g. a row/xid the view exposes), resolved to that record's commit LSN.

## G3. Resolution rule (the repair)

1. Resolve every offered locator independently to an LSN using ONLY the evidence/view.
2. If a locator cannot be resolved from the evidence (dangling / not present), it is **discarded with a recorded reason**; it does not by itself reject the answer.
3. Of the resolved locators, if they all point to the **same** commit LSN → that LSN is the accepted coordinate (`outcome=accepted`).
4. If resolved locators point to **different** commit LSNs that are genuinely distinct events → `refusal_parser` (the answer is truly ambiguous; this is the honest F1 distinction, preserved).
5. If no locator resolves → `refusal_parser`.
6. If the completion offers no coordinate and declines → `refusal_genuine` (unchanged from C3).

Timestamp-only answers resolve via G2.`ts`. Hex/int of the same LSN resolve to the same integer and therefore agree under rule 3. These two cases are exactly the P10 rejections this contract repairs.

## G4. Symmetry (anti-knob)

The grammar is applied **identically to R0 and R2 completions**. There is no representation-conditional branch. A parity guard fails closed if the extractor's behaviour depends on `representation`. This prevents "relax R0 only until it passes".

## G5. Determinism and scope

- Deterministic: same completion + same frozen view → same parse, byte-identical, on rebuild.
- Applies to the full P10 **submitted** set (every cell with a recorded completion). It does NOT invent parses for `infeasible_context` cells (no completion exists).
- Re-scoring after extraction uses the **unchanged P4 restore-validate oracle** and P4's lost-row rule on padded manifest rows, exactly as P10. The grammar changes only *which coordinate is extracted*, never how a coordinate is scored.

## G6. `rescoring-runs.jsonl` row shape (frozen)

```json
{
  "rescore_run_id": "rs-sc01-s100000-r0-gemma-k3",
  "source_scale_run_id": "sc01-s100000-r0-gemma-k3",
  "representation": "R0",
  "scale_target": 100000,
  "model_id": "gympc-gemma4-26b",
  "replicate": 3,
  "locators_offered": ["lsn_hex", "ts"],
  "locators_resolved_to": [8069841617, 8069841617],
  "grammar_outcome": "accepted",
  "p10_outcome": "refusal_parser",
  "outcome_changed": true,
  "verdict": "correct",
  "p10_verdict": null,
  "verdict_class_changed": true,
  "chosen_lsn_int": 8069841617,
  "oracle_optimum_lsn_int": 8069841617,
  "answer_blind_attested": true,
  "grammar_digest": "<sha256 of frozen answer-grammar.md at parse time>",
  "no_new_model_call": true
}
```

## G7. What the grammar MUST NOT do

- MUST NOT change the P1 results-row schema or any P10 sidecar. New data lives only in `rescoring-runs.jsonl`.
- MUST NOT rescue an answer by picking, among genuinely-distinct resolved LSNs, the one closest to the oracle optimum. Rule G3.4 forbids it and R002's answer-blind negative test proves it.
- MUST NOT introduce a new `incorrect_corrupt`; if a re-parse ever resolves to a damage-retaining coordinate, that is a real finding and is reported (H3 re-check), not suppressed.
