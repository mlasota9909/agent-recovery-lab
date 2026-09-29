# Tasks — P5: Representations R0 / R1 / R2 & the Identical Query Interface

Ordered and dependency-aware. Each task `Fnnn` has a work instruction at `work-instructions/WI-Fnnn.md` giving the
tier below this list: exact commands, artefacts, tier-labelled acceptance tests, a mandatory negative test, the review
bundle and an operator checklist.

**Run one task per agent invocation. Do not batch.**

Three entry conditions apply to every task: `bin/lab-ready` must exit 0 **and** the target SC-01 incident must have
passed `bin/lab-ledger-account` exactly-once; representations are built from the **default provenance-blind view only**;
and the git working tree must be clean before producing any provenance-bearing or fidelity-manifest artefact. No model
participates anywhere in P5.

## Phase A — Contracts and entry gate

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| F001 | Freeze `representation-interface.md` + `representation-fidelity.md`; record `lab-ready` 0, SC-01 reconciliation, and the default provenance-blind view name as the entry gate | — | the two contracts, entry-gate record | FR-1, AC-P5-01 |

> F001 freezes the interface envelope + probe set and the fidelity properties **before** any builder is written. Read
> both contracts line by line — the identical-envelope rule (interface R1/R2/R3) and the admissibility rule
> (fidelity §4) are the load-bearing parts.

## Phase B — The three representations

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| F002 | `bin/lab-repr-r0` — serialize provenance-blind events to a canonical LSN-ordered flat log; emit fidelity manifest | F001 | `bin/lab-repr-r0` | FR-2, AC-P5-02 |
| F003 | `bin/lab-repr-r1` — structured temporal ledger with derived per-window aggregates; emit fidelity manifest | F002 | `bin/lab-repr-r1` | FR-3, AC-P5-03 |
| F004 | `bin/lab-repr-r2` — deterministic causal graph + hierarchical template-rendered summaries; emit fidelity manifest | F002 | `bin/lab-repr-r2` | FR-4, AC-P5-04, AC-P5-05 |

> R0 is the base every other representation reconciles against, so it is built first. R1 and R2 both derive from the
> same event set. No model builds any of them; R2 summaries are template-rendered over exact aggregates.

## Phase C — The identical interface

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| F005 | `bin/lab-repr-query` — answer the fixed probe set identically across R0/R1/R2; per-probe telemetry | F002, F003, F004 | `bin/lab-repr-query` | FR-5, AC-P5-06, AC-P5-07 |

## Phase D — Verification of the load-bearing properties

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| F006 | determinism (byte-identical rebuild) + fidelity (reconciliation) + provenance-blindness | F002, F003, F004 | the honesty checks | FR-6, AC-P5-08, AC-P5-09, AC-P5-10, AC-P5-16 |
| F007 | the identical-interface parity test (envelope + probe set structurally identical; only content/telemetry differ) | F005 | the ablation-cleanliness proof | FR-7, AC-P5-11 |
| F008 | telemetry: exact `evidence_bytes` + pinned-tokenizer `token_estimate`; wire to results row; R2<R0 on recovery probe | F005 | the contribution measurement | FR-8, AC-P5-12, AC-P5-13 |

## Phase E — Headline and gate

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| F009 | SC-01 headline: all three answer the recovery probe faithfully + the R0-vs-R2 delta; discrimination negatives | F005, F006, F007, F008 | the tranche's proof | FR-9, AC-P5-14, AC-P5-15 |
| F010 | `bin/lab-verify-p5` tiered + read-only gate; all prior hashes re-verified; regression; P5 handoff | F001..F009 | `bin/lab-verify-p5`, handoff | FR-10, AC-P5-17, AC-P5-18, AC-P5-19 |

> F009 is the tranche's reason for existing. The operator will confirm all three representations point at the true
> SC-01 anomaly window, then confirm R2 presents far fewer evidence-bytes than R0 for the recovery-relevant probe.

## Dependency graph

```
F001 -- F002 --+-- F003 --+
               +-- F004 --+-- F005 --+-- F006
                                     +-- F007
                                     +-- F008 -- F009 -- F010
```

F003 and F004 may run in either order once F002 is complete. F005 needs all three. F006 needs the builders; F007 and
F008 need F005. F009 needs F005-F008. F010 runs last.

## Anti-goals for this tranche

Do not, in P5: modify any frozen contract or add a field to the results row / ledger-integrity / arm-coordinate
contract; invoke any language model or ML inference anywhere (no model builds a representation or writes a summary —
that is an Article I violation and defeats the experiment); build a representation from a principal-exposing view or let a
principal/usename/UID appear in any artefact, summary or response; let a representation omit ledger events or fabricate
an aggregate/summary figure; change the interface envelope or probe set between representations; build the Arm B model
harness or invoke a model to answer a probe (that is **P6**); build SC-02/03/04 representations (later tranches);
mistake the pinned `token_estimate` for the real model token count. If a task appears to require any of these, it has
been misread — record it in `observations.md` and continue within scope.
