# Plan — P6: Arm B, the modest-local-model harness

## Architecture decisions (locked)

These continue the ADR lineage (ADR-003 deterministic scoring; ADR-004 representation is the independent variable;
ADR-II provenance for scoring not detection; ADR-P5-1 identical interface; ADR-P5.1 model_view/reference split) and add
the decisions specific to running a stochastic subject honestly.

### ADR-P6-1 — one offline, pinned model; loopback only; no fine-tuning

Exactly one model is used for all of Arm B, declared by `model_id` + `quantization` + `weights_sha256`, invoked over a
loopback endpoint with greedy decoding (`temperature=0`), a fixed seed and fixed `max_tokens`. No sampling, no
fine-tuning, no adapter, no external API. This is sanctioned by the roadmap (the model is the point of Arm B) but is
the one place Article V's "stock mechanisms" admits a model — so it is pinned and declared, and offline-verified per
invocation (Article X). Changing the model or its weights is a superseding amendment that invalidates prior Arm B
results.

### ADR-P6-2 — the model is a subject behind the P5.1 guard, at a single choke point

The model is an experimental subject and must be blind to the answer. It is handed only the six-key `model_view` from
`bin/lab-repr-modelview`, and every byte that reaches it is assembled at exactly one place (`bin/lab-arm-b-prompt`)
that first calls `bin/lab-modelview-guard` (Article XVII). A repository scan proves there is no second assembly path.
This is the P6 analogue of the P0.1 receiver's single accepted command and directly answers the P5.1-review
carry-forward: the guard's value is realised only if every model-input path routes through it.

### ADR-P6-3 — separate model non-determinism from harness non-determinism

The harness (prompt assembly for a fixed model_view, extraction, scoring) is a deterministic pure function of its
inputs and is proven byte-identical on re-run over a *recorded* completion (AC-P6-12). The model's completion is the
only non-deterministic element; it is pinned as far as the runtime allows and its residual variability is measured by
K replicates (AC-P6-13), never blamed on or hidden by the harness. This is the honest way to verify a stochastic
subject inside a project that is otherwise byte-deterministic.

### ADR-P6-4 — a refusal is data; coercion is fabrication

The model may answer "I cannot determine a coordinate." That is recorded as `outcome="refusal"` with the raw
completion retained and scored as a refusal — it is **not** re-prompted, nudged, or replaced by a heuristic guess.
Coercing a refusal into a coordinate would fabricate a result and is prohibited (Article VIII). A refusal on R0 and a
determination on R2, for the same model, is itself a finding about the representation.

### ADR-P6-5 — score through the unchanged P4 path; emit the frozen arm-coordinate

Arm B does not get its own scorer. A determination's coordinate is handed to the existing P4 restore+validate path,
which produces the 4-level verdict, `damage_rows_retained` and `legit_rows_lost` exactly as it does for Arm A. Arm B
emits the frozen `arm-coordinate` shape (`arm=arm_b`, `representation` in {R0,R1,R2}) with `selection_inputs.read_*`
all false. This is what lets P7/P8 compare Arm A and Arm B on identical footing.

### ADR-P6-6 — capture the real token count now; it closes the P5 estimate

P5 recorded a pinned-tokenizer `token_estimate` and explicitly deferred the real, model-specific token count to P6
(ADR-P5-5). P6 records the runtime-reported `prompt_tokens` per run and stores it distinct from the P5 estimate, so
both can be reported (the estimate for model-independence, the real count for the actual model). They are not
conflated.

### ADR-P6-7 — the frozen-headline state is the operating state, not a fault

`bin/lab-ready` exits 1 because the SC-01 headline ledger is frozen (0444, consumer stopped) to keep the reconciled
incident byte-identical for P3/P4/P5. P6 operates in exactly this state: it queries materialised representations and
scores through the P4 restore path (which restores into an isolated sandbox and never touches the victim), so it needs
no live consumer. The entry gate is `bin/lab-regression` green plus admissible representations — never "start the
consumer to clear lab-ready".

## No new constitutional article

P0.1, P1.1, P2.1, P3.1 and P5.1 each added an article because each was a remediation that surfaced a defect class
(XII test hatches, XIII verification tiers, XIV provenance of record, XV amend-by-supersession, XVI read-only gates,
XVII subject-visible surface). P6 is a forward build and surfaces no new class; it operates under the seventeen articles
in force. The model-pinning, single-choke-point, harness-determinism and refusal-integrity rules (ADR-P6-1..4) are
strong ADRs enforced mechanically, not new articles. If P6's own acceptance review finds a defect class the gate
missed — the recurring pattern in this project — that is where Article XVIII would come from, not before.

## Task breakdown

| Task | Owns | Serves |
| --- | --- | --- |
| H001 | the two P6 contracts + entry-gate record + discovered model pinning | FR-1 |
| H002 | `bin/lab-model` — offline pinned invocation + verbatim I/O + offline proof | FR-2 |
| H003 | `bin/lab-arm-b-prompt` — the single guarded prompt-assembly choke point | FR-3 |
| H004 | `bin/lab-arm-b-extract` — deterministic extraction into arm-coordinate; refusal on ambiguity | FR-4 |
| H005 | `bin/lab-arm-b` — refusal-aware run driver, K replicates | FR-5 |
| H006 | verbatim provenance-blind rationale capture wired to arm-coordinate | FR-6 |
| H007 | real token + latency telemetry to the results row; distinct from P5 estimate | FR-7 |
| H008 | scoring wiring through the unchanged P4 path; emit frozen arm-coordinate | FR-8 |
| H009 | SC-01 headline: R0/R1/R2 x K, objective error vs ground truth, discrimination negatives | FR-9 |
| H010 | `bin/lab-verify-p6` gate; contract re-verify; regression; P6 handoff | FR-10 |

## Sequencing

H001 first (contracts + model pinning before any invocation). H002 (the model wrapper) precedes everything that calls
the model. H003 (the guarded prompt) depends on H002 and the P5.1 guard. H004 (extraction) depends on the protocol and
can be built/tested against recorded completions. H005 (the run driver) composes H002+H003+H004. H006 and H007 depend
on H005's run records. H008 (scoring) depends on H004's coordinate + the P4 path. H009 (headline) depends on
H005..H008. H010 gates and runs last.

```
H001 -- H002 -- H003 --+
                       +-- H005 --+-- H006
        H004 ----------+          +-- H007
                       H004 -- H008 --+
                                      +-- H009 -- H010
```

## Risks

- **A second path reaches the model without the guard.** The highest-consequence risk and the exact P5-review class:
  the guard exists but something bypasses it. Mitigation: ADR-P6-2 + the H003 single-choke-point scan and the
  inject-`answer` negative (AC-P6-03, AC-P6-04, AC-P6-15).
- **A refusal is coerced into a guess to "get a result".** Would fabricate data and inflate Arm B. Mitigation:
  ADR-P6-4 + the refusal-is-first-class rule + the coerced-guess negative (AC-P6-07).
- **Model non-determinism blamed on / masked by the harness.** Mitigation: ADR-P6-3 + harness-determinism proof over a
  recorded completion (AC-P6-12) + K replicates reporting agreement (AC-P6-13).
- **An outbound model call (cloud API, telemetry, model download mid-run).** Article X violation. Mitigation:
  ADR-P6-1 + per-invocation outbound-socket check (AC-P6-02).
- **Provenance leaks into the prompt or rationale.** Would hand the model the answer key. Mitigation: ADR-P6-2 + the
  guard + the rationale blindness scan + inject-a-principal negative (AC-P6-08, AC-P6-15).
- **Someone modifies the P4 path to make Arm B look better.** Mitigation: ADR-P6-5 + P4 gate-hash re-verification
  (AC-P6-10, AC-P6-18).
- **String LSN comparison in extraction/resolution.** Mitigation: integer LSN via `bin/lab-coordinate`; the `3/9` vs
  `3/10` trap covered in the extraction test (H004).
- **Model token budget vs representation size.** R0's raw log may exceed the context window; that is itself a finding
  (R0 may be un-ingestible, forcing a refusal or truncation). Record it honestly rather than silently truncating; if
  truncation is unavoidable, it is declared in the run record and discussed as a limitation, not hidden.

## Carry-forward from the P5.1 review

- **The guard must sit at the single choke point where the model prompt is assembled, with a test that no other
  assembly path exists** — implemented as ADR-P6-2 and AC-P6-04. This is the explicit promise made in the P5.1 review.
- **Record any sensible substitution as an amendment, not a buried note (Article XV).** If a P6 builder must deviate
  from a frozen contract (it should not), supersede via an amendment file with its own ADR; never edit a frozen file
  and never bury the change in a handoff note (the P2 `xid` and P4 sandbox-location lessons).
- **Fixture drift.** The per-tranche regression fixtures are pinned. P6 adds no ledger schema change and must not
  re-pin a fixture; if it somehow must, state why in the handoff (H010).
