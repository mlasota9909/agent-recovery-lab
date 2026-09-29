# Tasks — P6: Arm B, the modest-local-model harness

Ordered and dependency-aware. Each task `Hnnn` has a work instruction at `work-instructions/WI-Hnnn.md` giving the
tier below this list: exact commands, artefacts, tier-labelled acceptance tests, a mandatory negative test, the review
bundle and an operator checklist.

**Run one task per agent invocation. Do not batch.**

Entry conditions apply to every task: `bin/lab-regression` green (NOT `lab-ready`, which is expected to exit 1 due to
the frozen headline); the SC-01 representations R0/R1/R2 exist and are admissible; the offline model runtime is healthy
and provably offline; and the git working tree is clean before producing any provenance-bearing or results artefact.
The model sees only `model_view`, always through `bin/lab-modelview-guard`.

## Phase A — Contracts, model pinning and entry gate

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| H001 | Freeze `model-runtime.md` + `arm-b-protocol.md`; discover and record the model id/quantisation/weights hash; record the entry gate (regression green, SC-01 admissible, model offline) | — | the two contracts, model pinning, entry-gate record | FR-1, AC-P6-01 |

> H001 fixes what the model is and how Arm B is procedurally run **before** any invocation. Read both contracts line by
> line — the pinning rule (`model-runtime` R1/R2/R4) and the single-choke-point + refusal rules (`arm-b-protocol`
> R2/R4/R5) are the load-bearing parts.

## Phase B — The offline model and the guarded prompt

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| H002 | `bin/lab-model` — invoke the pinned model over loopback, greedy+seed, capture verbatim I/O + real tokens + latency, verify no outbound socket | H001 | `bin/lab-model` | FR-2, AC-P6-02 |
| H003 | `bin/lab-arm-b-prompt` — the single guarded prompt-assembly path; identical across R0/R1/R2 except `content`; calls the guard | H001, H002 | `bin/lab-arm-b-prompt` | FR-3, AC-P6-03, AC-P6-04, AC-P6-05 |

> H003 is the integrity keystone. There must be exactly one place that builds model input and it must call
> `bin/lab-modelview-guard`. The scan proving no bypass exists is the P6 analogue of the P0.1 single-append-command.

## Phase C — Extraction and the refusal-aware driver

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| H004 | `bin/lab-arm-b-extract` — deterministic parse of the final tagged line into the frozen arm-coordinate; ambiguity -> refusal | H001 | `bin/lab-arm-b-extract` | FR-4, AC-P6-06, AC-P6-07 |
| H005 | `bin/lab-arm-b` — run K replicates per representation; record determinations and refusals; never coerce | H002, H003, H004 | `bin/lab-arm-b` | FR-5, AC-P6-13 (partial) |

## Phase D — Capture, telemetry and scoring

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| H006 | verbatim provenance-blind rationale capture wired to `arm-coordinate.rationale` | H005 | rationale capture | FR-6, AC-P6-08 |
| H007 | real `prompt_tokens` + `latency_ms` to the results row; recorded distinct from P5's pinned estimate | H005 | telemetry wiring | FR-7, AC-P6-09 |
| H008 | scoring wiring: extracted coordinate through the UNCHANGED P4 restore+validate path; emit frozen arm-coordinate | H004 | scoring wiring | FR-8, AC-P6-10, AC-P6-11, AC-P6-12, AC-P6-16 |

## Phase E — Headline and gate

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| H009 | SC-01 headline: same model over R0/R1/R2 x K, objective error vs ground truth, appended automatically; discrimination negatives (guard bypass, coerced refusal, provenance leak) | H005, H006, H007, H008 | the tranche's proof | FR-9, AC-P6-13, AC-P6-14, AC-P6-15 |
| H010 | `bin/lab-verify-p6` tiered + read-only gate; all prior hashes re-verified; regression; P6 handoff | H001..H009 | `bin/lab-verify-p6`, handoff | FR-10, AC-P6-17, AC-P6-18, AC-P6-19 |

> H009 is the tranche's reason for existing. The operator will confirm the R0/R1/R2 coordinate errors are computed
> against ground truth from machine-readable fields and appended automatically, and that the three discrimination
> negatives (a bypassed guard, a coerced refusal, an injected principal) are each caught.

## Dependency graph

```
H001 -- H002 -- H003 --+
                       +-- H005 --+-- H006
        H004 ----------+          +-- H007
                       H004 -- H008 --+
                                      +-- H009 -- H010
```

H004 may be built and tested against recorded completions in parallel with H002/H003. H005 composes H002+H003+H004.
H006/H007 need H005's records; H008 needs H004's coordinate + the P4 path. H009 needs H005..H008. H010 runs last.

## Anti-goals for this tranche

Do not, in P6: modify any frozen contract or add a field to the results row / arm-coordinate / representation-interface
contracts; modify the P4 restore+validate path, the representations, or the guard; hand the model anything but a
guarded `model_view` (no `answer`, no `reference`, no coordinate field, no provenance — Article XVII); build a second
prompt-assembly path that bypasses the guard; coerce a refusal into a guessed coordinate (Article VIII); fine-tune,
train, add an adapter, enable sampling, or make any outbound model call (Article X); start the consumer to clear
`lab-ready` (the frozen-headline state is expected); run SC-02/03/04 or the full matrix (that is **P7**); re-open or
re-tune Arm A. If a task appears to require any of these, it has been misread — record it in `observations.md` and
continue within scope.
