# Plan — P5: Representations R0 / R1 / R2 & the Identical Query Interface

## Architecture decisions (locked)

These continue the ADR lineage (ADR-003 deterministic scoring; ADR-004 representation is the independent variable;
ADR-008 the cross-layer coordinate; ADR-II provenance for scoring not detection) and add the decisions specific to
building the representations and their interface.

### ADR-P5-1 — the interface is identical; only content and telemetry vary

The independent variable is the representation, so everything else must be held constant. One request envelope, one
response envelope, one fixed probe set (`representation-interface.md`), presented identically across R0/R1/R2. A
representation may return different `content` and will report different `telemetry`; it may not change the shape of the
conversation. This is what lets P6 attribute a difference in the model's success to the representation and nothing
else. Enforced by the parity test (F007), not by inspection.

### ADR-P5-2 — deterministic construction, no model in the loop

The R2 graph edges and every hierarchical summary are computed by fixed rules and rendered from fixed string templates
over exact aggregates. No language model participates in building any representation (Article I). This is the single
most important soundness decision in the whole experiment: because nothing is learned, the question of how R2
generalises from training data does not arise — there is none. Determinism is proven by byte-identical rebuild (F006), and
`built_by_model=false` is a mandatory, checked manifest field with the build command log showing no model call.

### ADR-P5-3 — fidelity: a representation may neither omit nor fabricate

A representation that quietly dropped the confusing legitimate traffic, or invented an anomaly, could "help the model"
for the wrong reason and destroy the experiment's validity. So every ledger event is represented (R0 count == ledger
count), and every R1 aggregate and every R2 summary figure reconciles **exactly** to the underlying events. A summary
that says "201 deletes in window 15" is backed by exactly 201 delete events or the manifest reports `reconciles=false`
and the representation is inadmissible. Enforced in F006 with an off-by-one negative test.

### ADR-P5-4 — provenance-blind, built from the default principal-free view only

The model in P6 must not be able to read *who* made a change — only *what* changed and *when* (Article II). Every
representation is built from the default provenance-blind ledger view, and a structured scan plus a token scan prove no
`principal`/`usename`/`session_user`/UID appears in any artefact, summary, node/edge label or query response. The
negative test injects a principal and proves it is caught. This is the P5 realisation of the same rule that keeps Arm A
honest in P3.

### ADR-P5-5 — evidence_bytes is the primary telemetry; token_estimate is a declared, pinned estimate

The contribution is measured as the evidence a modest model must read to find the recovery point. The exact,
model-independent measure is `evidence_bytes` (UTF-8 byte length of the `content` surfaced). A `token_estimate` is also
recorded, produced by **one vendored, pinned tokenizer** (name+version recorded) so it is deterministic and comparable
across arms — but it is explicitly an estimate, not the exact tokens the eventual P6 model will consume; the real,
model-specific token count is captured in P6 when the model runs. Asserting `evidence_bytes` as primary keeps the P5
claim model-independent and sound. The recovery-relevant probe must show R2 < R0 on both measures (AC-P5-13).

### ADR-P5-6 — the R2 summaries are template-rendered, not free text

R2's "GraphRAG-style" summaries are rendered from fixed templates with slots filled by exact aggregates (e.g.
`Window {i} [{lo}..{hi}]: {n_del} DELETE on relation {rel}, {n_ins} legitimate INSERT; anomaly {score}`). This gives a
modest model the "read a short summary, not 900 raw lines" benefit while remaining byte-for-byte reproducible and fully
reconcilable to the events. Free-form or model-authored summaries are prohibited (they would violate ADR-P5-2 and
ADR-P5-3).

### ADR-P5-7 — representations are incident-scoped and reuse the existing coordinate resolver

One `var/repr/<incident>/{R0,R1,R2}/` set per incident. Any window bound or candidate coordinate a representation
surfaces is resolved with the existing `bin/lab-coordinate` (integer LSN, newest snapshot with LSN <= target); P5 does
not invent a second resolver. Grouping by `incident_id` is what lets P6 prove R0/R1/R2 saw the same incident rather
than three separately generated ones.

## No new constitutional article

P0.1, P1.1, P2.1 and P3.1 each added an article because each was a remediation that surfaced a defect class (XII test
hatches, XIII verification tiers, XIV provenance of record, XV amend-by-supersession, XVI read-only gates). P5 is a
forward build and surfaces no new class; it operates under the sixteen articles in force. The identical-interface and
deterministic-construction rules (ADR-P5-1, ADR-P5-2) are strong ADRs enforced mechanically, not new articles. If P5's
own acceptance review finds a defect class the gate missed — the pattern in several earlier tranches — that is where
Article XVII would come from, not before.

## Task breakdown

| Task | Owns | Serves |
| --- | --- | --- |
| F001 | the two P5 contracts + entry-gate record | FR-1 |
| F002 | `bin/lab-repr-r0` — flat chronological event log | FR-2 |
| F003 | `bin/lab-repr-r1` — structured temporal ledger + aggregates | FR-3 |
| F004 | `bin/lab-repr-r2` — deterministic causal graph + summaries | FR-4 |
| F005 | `bin/lab-repr-query` — the identical query interface + telemetry | FR-5 |
| F006 | determinism + fidelity + provenance-blindness verification | FR-6 |
| F007 | the identical-interface parity test | FR-7 |
| F008 | telemetry: evidence_bytes + pinned-tokenizer token_estimate, wired to the results row | FR-8 |
| F009 | SC-01 headline: faithful answer across all three + the R0-vs-R2 delta | FR-9 |
| F010 | `bin/lab-verify-p5` gate; contract re-verify; regression; P5 handoff | FR-10 |

## Sequencing

F001 first (contracts before any builder). F002 (R0) is the base the others reconcile against, so it precedes F003 and
F004. F005 (the interface) depends on all three representations existing. F006 (determinism/fidelity/blindness) depends
on the builders; F007 (parity) and F008 (telemetry) depend on the interface (F005). F009 (headline) depends on F005-F008.
F010 gates and runs last.

```
F001 -- F002 --+-- F003 --+
               +-- F004 --+-- F005 --+-- F006
                                     +-- F007
                                     +-- F008 -- F009 -- F010
```

## Risks

- **Interface differs across representations, silently.** The highest-consequence risk: if the envelope or probe set
  is not truly identical, a P6 result is confounded by the interface. Mitigation: ADR-P5-1 + the F007 parity test that
  diffs the response envelope structurally across R0/R1/R2 and a negative test that adds a distinguishing field and
  proves it is caught.
- **A model sneaks into R2 construction.** Would make R2 non-deterministic and unsound. Mitigation: ADR-P5-2 +
  `built_by_model=false` checked + byte-identical rebuild (F006) + a build command-log scan for any model invocation.
- **A representation fabricates or omits to look helpful.** Mitigation: ADR-P5-3 + reconciliation of every aggregate/
  summary to the events + the off-by-one negative test (F006/F009) + `event_count==ledger_event_count`.
- **Provenance leaks into a summary or node label.** Would hand the model the answer key. Mitigation: ADR-P5-4 + the
  structured+token blindness scan + the inject-a-principal negative test.
- **Token estimate mistaken for the real model token count.** Mitigation: ADR-P5-5 — `evidence_bytes` is primary and
  model-independent; `token_estimate` is a declared, pinned estimate, with the real count captured later in P6.
- **String LSN comparison in window ordering.** Mitigation: integer LSN only; the `3/9` vs `3/10` trap is covered in
  the window-ordering test (F003).
- **Read-only gate cost as ledgers grow.** The blindness/fidelity scans read whole artefacts. If gate time balloons on
  SC-02+ ledgers, scope the scan to the incident under test — a known lever, not needed now.

## Carry-forward from the P4 review

- **Record any sensible substitution as an amendment, not a buried note (Article XV).** If a P5 builder must deviate
  from a frozen contract (it should not), supersede via an amendment file with its own ADR; never edit the frozen file
  and never bury the change in a handoff note. This is the P2 `xid` lesson.
- **Fixture drift.** The per-tranche regression fixtures are pinned. P5 adds no ledger schema change and must not
  re-pin a fixture; if it somehow must, state why in the handoff (F010).
