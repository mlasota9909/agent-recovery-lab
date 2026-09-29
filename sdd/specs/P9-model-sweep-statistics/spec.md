# P9 — Model Sweep + Statistics : SPECIFICATION

## Problem
The validated recovery result rests on ONE model and ONE fully-validated scenario, with
K=5 rates reported without uncertainty, and the representation ordering is theoretically
dismissible as a single-model prompt artefact. The research contribution is sound but
its strongest empirical claim is currently over-scoped and under-tested.

## Objective
Add the minimum experimental + analytical work that maximally strengthens the evidence in
one week: (1) replicate the R0/R1/R2 ablation across 3 distinct models/families through
the identical interface; (2) analyse under a pre-registered statistics plan; (3) frame
Arm A vs Arm B as correctness-vs-interpretation; (4) position the work against 2025-26
systems. No new recovery mechanism is built.

## In scope
- Cross-model sweep on SC-01 (SC-02 optional if throughput permits).
- Pre-registered paired statistics with CIs, effect size, Holm correction.
- Arm A vs Arm B head-to-head analysis and the interpretation-layer framing.
- Read-only reuse of all prior evidence, ledgers, representations, oracle, P4 path.

## Out of scope
- New scenarios beyond SC-01/SC-02; new representations; model fine-tuning; temperature
  sweeps; any change to prior frozen contracts except additive supersession.

## Functional requirements
- FR-1  Freeze model-sweep-plan, statistical-analysis-plan (pre-registered), and one
        reserved contract; add Article XXI. (N001)
- FR-2  Register/verify 3 distinct models (weights hash, containment, greedy+seed),
        recording family/tokenizer; refuse if two share a tokenizer_id or <2 families. (N002)
- FR-3  Re-assert model_view interface parity across ALL models, and re-assert R0/R1/R2
        artefact hashes byte-identical to their P5/P5.1 close. (N003)
- FR-4  Execute the sweep (SC-01[/SC-02] x R0/R1/R2 x 3 models x K=5) through the guard,
        appending rows tagged sweep_id; resumable; run_failure rows retained. (N004)
- FR-5  Run the pre-registered analysis; refuse if plan digest changed post-collection;
        emit CIs, effect sizes, Holm-corrected tests, and the pre-declared interpretation. (N005)
- FR-6  Produce the Arm A vs Arm B head-to-head table and the correctness-vs-interpretation
        framing, grounded in VerifyRCA/VeriOps. (N006)
- FR-7  Reserved; outside the scope of this repository. (N007)
- FR-8  Tiered acceptance gate + close-out memo; all prior contract hashes re-verified. (N008)

## Acceptance criteria
- AC-P9-01 (M) Article XXI appended; three contracts frozen with pinned digests; plan
  frozen BEFORE any sweep row exists (timestamp/commit ordering proven).
- AC-P9-02 (M) 3 models registered; tokenizer_ids distinct; >=2 families; each weights_sha256
  recorded; containment re-verified per model (no public egress during an invocation;
  cloud alias refused).
- AC-P9-03 (M) model_view parity: for a fixed representation, the bytes handed to each
  model are structurally identical (only content differs by representation, nothing by
  model). Negative test: injecting a per-model structural field is caught.
- AC-P9-04 (M) R0/R1/R2 artefact hashes byte-identical to P5/P5.1 close.
- AC-P9-05 (M) guard blocks the reference answer for every model input path
  (Article XVII); negative test splices an answer and is refused.
- AC-P9-06 (M) sweep completeness: rows = planned; determination/refusal/run_failure
  partition recorded; refusals retained as data; determinations scored via the P4 path.
- AC-P9-07 (M) analysis refuses to run if statistical-analysis-plan digest changed after
  first sweep row (negative test mutates the plan and proves refusal).
- AC-P9-08 (M) paired tests + bootstrap CIs + Cliff's delta + Holm correction produced
  from the pre-registered plan; every reported number regenerates byte-identical.
- AC-P9-09 (M) the pre-declared interpretation matching the observed outcome is emitted
  verbatim; no universal language attached to n=1-scenario evidence (lint check).
- AC-P9-10 (M) Arm A vs Arm B head-to-head table computed from rows; framing states LLM =
  interpretation/accessibility layer, deterministic = correctness layer.
- AC-P9-11 (A) reserved; outside the scope of this repository.
- AC-P9-12 (M) read-only: whole-of-prior-evidence + results-rows manifest byte-identical
  before/after the tranche (new rows appended only to sweep outputs / sidecar).
- AC-P9-13 (M) close-out memo: per-tier totals, validity partition, pre-registered
  conclusion, and honest scope statement; no undifferentiated pass total.
