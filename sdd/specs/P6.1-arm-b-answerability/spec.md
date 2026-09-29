# Spec — P6.1: Arm B Answerability (diagnose the null, correct containment, make the task answerable)

**Feature ID:** P6.1-arm-b-answerability
**Status:** ready for implementation
**Owner:** Maciej Lasota
**Depends on:** P6 (accepted, pending this remediation)
**Blocks:** P7 (the run matrix) — P7 drives Arm B across SC-01..SC-04, so Arm B must produce interpretable signal on
SC-01 first, and the containment claim must be true, before the matrix is run.

## 1. Purpose

Turn the P6 apparatus from mechanically-correct-but-silent into a source of real signal, without changing the model or
the representations. Establish, from the verbatim completions, *why* every Arm B run refused (D1); correct the model
containment contract and its check so they assert what the cross-host deployment actually guarantees (D2); broaden the
Arm B answer grammar and relax the task framing so the recovery task is answerable from each representation's own
vocabulary while remaining byte-identical across R0/R1/R2, refusal-preserving, and answer-blind; then re-run SC-01
Arm B to produce the real R0-vs-R1-vs-R2 headline. Add the constitutional principle that a null result must be
root-caused before it is reported.

## 2. Problem statement

**D1 — total null, reported without root cause.** `logs/review/H009/headline.json` records R0 `determinations:0,
refusal_rate:1.0` (evidence_bytes 43,468; prompt_tokens_real 17,893), R1 `determinations:0, refusal_rate:1.0` (245;
220), R2 `determinations:0, refusal_rate:1.0` (304; 241). Zero determinations across all three representations and all
replicates means no ablation result exists. The model context window is 262,144 tokens, so R0's 17,893 tokens is ~7%
of context: this is **not** overflow. R0 carried canonical hex LSNs and still refused every replicate, so a
representation-vocabulary mismatch alone cannot explain it either — the shared prompt and the answer-extraction grammar
are implicated. The gate passed 19/19 because it verifies mechanics and records refusals honestly; it never asserted
signal. A null that passes a green gate is not a finding until its proximate cause is established from the completions
and the instrument (prompt + grammar) is ruled out or corrected.

**D2 — containment check verifies a property the deployment lacks.** `model-runtime` R2 requires a loopback-bound
runtime with no outbound connection; `offline_verified` was recorded true. The real path is cross-host: LiteLLM
`c220m3:4001` fronting vLLM `gb10a:8000`. A cross-host call is not loopback-only, so the check measured a narrower
property than the contract states. The topology is a legitimate private-lab arrangement; the contract and check must be
corrected to assert what actually holds: the endpoint is on the private lab network (not a public/cloud address), no
public-internet egress occurs during an invocation, the cloud alias `deepseek-v4-pro` is not the target, and the local
weights hash is unchanged.

## 3. Scope

### In scope

- **Article XVIII** added to the constitution: a null or degenerate result must be root-caused and the instrument ruled
  out before it is reported as a finding.
- **J001 diagnosis**: classify each of the 15 H009 completions to a proximate refusal cause from the verbatim bytes,
  using a fixed taxonomy; record counts per representation; ADR-P6.1-1 (the null root cause + finding), ADR-P6.1-2
  (containment topology correction), ADR-P6.1-3 (answer-grammar/task-framing fix design), ADR-P6.1-4 (corrected never
  weakened; re-run invalidates the prior null).
- **`model-runtime.amendment-1.md`** (Article XV supersession): records the real cross-host topology; redefines the
  containment property from loopback-only to private-lab-network-only + no-public-egress + no-cloud-alias +
  fixed-weights; original `model-runtime.md` byte-identical.
- Rewrite the containment check in `bin/lab-model` (or a dedicated `bin/lab-model-containment`) to verify the redefined
  property per invocation, recording `containment_verified` with the specific checks that passed.
- **`arm-b-protocol.amendment-1.md`**: broadens the R4 extraction grammar to a resolvable locator —
  `COORDINATE:` carrying at least one of `window=<int>`, `lsn=<hex-or-int>`, `ts=<iso8601>` — resolved to the frozen
  coordinate via `bin/lab-coordinate`; relaxes §2 task framing so the task is answerable from each representation's own
  vocabulary; keeps R1 (prompt byte-identical across R0/R1/R2 except `content`), R5 (refusal first-class), R2 (single
  guarded assembly path) intact. Original `arm-b-protocol.md` byte-identical.
- Rebuild `bin/lab-arm-b-prompt` and `bin/lab-arm-b-extract` to the amended grammar and framing.
- **J004 re-run**: SC-01 Arm B across R0/R1/R2 × K on the fixed harness; new `headline.json`; prior null quarantined as
  superseded (retained, not deleted); harness determinism (R7) and replicate agreement (R8) preserved; scoring via the
  unchanged P4 restore+validate path.
- `bin/lab-verify-p6.1` gate; a re-derived `bin/lab-verify-p6` consistent with the amendments; old→new criterion
  mapping; acceptance memo "P6 accepted only after P6.1".

### Out of scope

- Any change to a frozen contract file (supersede by amendment only).
- Rebuilding, re-fitting, enriching or shrinking any R0/R1/R2 representation artefact (frozen; hashes must re-verify).
- Installing, swapping, fine-tuning or adapting the model (Article I / model-runtime R3).
- Coercing a refusal into a guess, or re-prompting after a refusal (Article VIII / arm-b-protocol R5).
- Letting the broadened grammar admit the reference answer or any pre-computed result (Article XVII — guard still binds).
- Reading `principal` in any path (Article II).
- Making any criterion pass by weakening what it checks.

## 4. Functional requirements

- **FR-1 Null-diagnosis principle.** The constitution gains Article XVIII: a null, empty, or degenerate result MUST be
  diagnosed to a proximate cause established from primary evidence, and the instrument (harness, prompt, grammar,
  measurement path) MUST be ruled out as the cause, before the result is reported as a finding about the subject.
- **FR-2 Completion-level diagnosis.** Every H009 completion (R0/R1/R2 × K) is classified to exactly one proximate
  cause from a fixed taxonomy — `grammar-noncompliance` (an answer was given but not in the tagged form the extractor
  requires), `vocabulary-mismatch` (the requested locator form is absent from this representation's content),
  `explicit-refusal` (the model emitted a REFUSAL line on reasoning grounds), `task-infeasible-claim` (the model
  asserted the evidence is insufficient), `other` — from the verbatim bytes, with counts per representation.
- **FR-3 Containment corrected by amendment.** `model-runtime.amendment-1.md` records the cross-host topology and
  redefines the containment property to: endpoint on the private lab network (not a public/cloud address); no
  public-internet egress observed during an invocation; the cloud alias not targeted; local weights hash unchanged. The
  original contract stays byte-identical.
- **FR-4 Containment check verifies the truth.** The rewritten check verifies each element of the redefined property
  per invocation and records `containment_verified:true` only when all pass; a public-endpoint or cloud-alias target
  makes it refuse.
- **FR-5 Answer grammar broadened, not loosened.** `arm-b-protocol.amendment-1.md` accepts a resolvable locator (window
  / LSN hex-or-int / timestamp), each resolved by `bin/lab-coordinate`. An empty, ambiguous, or unresolvable locator is
  still a refusal (R5). The grammar admits no `answer`/`reference`/`candidates` structure — the guard still binds.
- **FR-6 Task answerable from every representation, identically framed.** The relaxed prompt is byte-identical across
  R0/R1/R2 except `content` (R1); it asks for whichever locator the evidence provides and states refusal is permitted
  only when the evidence genuinely does not localise a safe point.
- **FR-7 Re-run and honest headline.** SC-01 Arm B is re-run R0/R1/R2 × K; `headline.json` reports per-representation
  determination/refusal rates, and for determinations the P4 verdict, `damage_rows_retained`, `legit_rows_lost`, and
  coordinate error vs ground truth. Any residual refusal is reported with its J001-taxonomy cause, not hidden. The prior
  null headline is retained as `headline.superseded.json` with a pointer.
- **FR-8 Determinism and blindness preserved.** Given a fixed completion, prompt assembly, extraction and scoring are
  byte-identical on re-run (R7). Replicate agreement is computed from the K records (R8). No model input contains a
  provenance token (Article II) or the reference answer (Article XVII).
- **FR-9 Gate and memo.** `bin/lab-verify-p6.1` runs every P6.1 criterion with per-tier totals; re-verifies all prior
  contract hashes unchanged; runs `bin/lab-gate-readonly-check` against itself and `bin/lab-verify-p6`; records the
  old→new criterion mapping and the acceptance memo "P6 accepted only after P6.1".

## 5. Acceptance criteria

| ID | Tier | Requirement |
| --- | --- | --- |
| AC-P6.1-01 | M | `constitution.md` contains a well-formed Article XVIII (null results root-caused before reported); article count is 18 |
| AC-P6.1-02 | M | ADR-P6.1-1 records the null root cause with per-representation completion counts; ADR-P6.1-2 the containment correction; ADR-P6.1-3 the grammar/framing fix; ADR-P6.1-4 corrected-never-weakened + re-run-invalidates-null |
| AC-P6.1-03 | M | `logs/review/J001/refusal-diagnosis.json` classifies all 15 H009 completions to exactly one taxonomy cause each, re-derivable from the retained completion bytes; per-representation counts sum to K each |
| AC-P6.1-04 | M | `model-runtime.amendment-1.md` exists, records the cross-host topology, and redefines containment to {private-network endpoint, no public egress, no cloud alias, fixed weights}; original `model-runtime.md` byte-identical (H001 hash re-verifies) |
| AC-P6.1-05 | M | The containment check records `containment_verified:true` with each sub-check named, for a real invocation to the pinned endpoint |
| AC-P6.1-06 | M | NEGATIVE: pointing the containment check at a public/cloud address (or the `deepseek-v4-pro` alias) makes it exit non-zero naming the violated sub-check; reverting passes again |
| AC-P6.1-07 | M | `arm-b-protocol.amendment-1.md` exists; defines the resolvable-locator grammar (window / LSN hex-or-int / ts) and the relaxed task framing; original `arm-b-protocol.md` byte-identical (H001 hash re-verifies) |
| AC-P6.1-08 | M | `bin/lab-arm-b-extract` resolves each locator form to the same coordinate via `bin/lab-coordinate`; an empty/ambiguous/unresolvable locator yields `outcome=refusal` with `lsn_int=null` (no guess) |
| AC-P6.1-09 | M | Prompt byte-identical across R0/R1/R2 except `content` (H003 diff re-derived on the amended template) |
| AC-P6.1-10 | M | Every assembled model input still passes `bin/lab-modelview-guard`; the broadened grammar admits no `answer`/`reference`/`candidates` structure |
| AC-P6.1-11 | M | NEGATIVE: an assembled prompt with a spliced reference `answer` is refused by the guard; a completion emitting only a bare `REFUSAL` still records a refusal (not a guess); reverting each passes again |
| AC-P6.1-12 | M | R0/R1/R2 representation artefacts byte-identical to their P5/P5.1 close (F002/F003/F004 hashes re-verify); no representation rebuilt, enriched, or shrunk |
| AC-P6.1-13 | M | J004 re-run `headline.json` reports per-representation determination/refusal rates and, for determinations, P4 verdict + `damage_rows_retained` + `legit_rows_lost` + coordinate error vs ground truth, re-derived from committed arm records |
| AC-P6.1-14 | M | Harness determinism (R7): re-running extraction+scoring over a recorded completion yields byte-identical coordinate and score; replicate agreement (R8) computed from the K records |
| AC-P6.1-15 | M | Provenance-blindness (Article II): no `principal`/`usename`/`session_user`/UID in any assembled prompt or rationale, across all re-run records |
| AC-P6.1-16 | M | Prior null retained as `logs/review/H009/headline.superseded.json` (or equivalent) with a pointer to the J004 re-run; not deleted |
| AC-P6.1-17 | M | No frozen contract file mutated (all prior hashes re-verify); old→new criterion mapping records the containment redefinition and grammar broadening as corrected/strengthened, none weakened |
| AC-P6.1-18 | M | `bin/lab-verify-p6` re-derived consistent with the amendments; `bin/lab-verify-p6.1` reports every criterion PASS with per-tier totals printed separately, exit 0; both pass `bin/lab-gate-readonly-check` |
| AC-P6.1-19 | A | `docs/p6-acceptance-memo.md` records the two remediated defects and `p6_accepted_only_after: "P6.1"` on machine-readable fields |

All criteria are tier M except AC-P6.1-19, which attests a one-time documentation event and still asserts on JSON
fields, per Article XIII.

## 6. Definition of done

`bin/lab-verify-p6.1` green with per-tier totals; Article XVIII in force; the null diagnosed to per-completion causes;
containment contract and check corrected by amendment to the truth of the cross-host deployment, with the original
byte-identical; the answer grammar broadened to a resolvable locator and the task framing relaxed, byte-identical
across R0/R1/R2, refusal still first-class, guard still binding; SC-01 Arm B re-run with an honest headline and any
residual refusal diagnosed; representations byte-identical to their P5/P5.1 close; determinism and blindness preserved;
all frozen contract files unchanged; no criterion weakened; prior null retained; acceptance memo updated.
