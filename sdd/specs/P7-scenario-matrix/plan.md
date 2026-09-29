# Plan — P7: Scenario expansion and the run matrix

## Architecture decisions (locked)

These continue the ADR lineage (ADR-003 deterministic scoring; ADR-004 representation is the independent variable;
ADR-II provenance for scoring not detection; ADR-P5-1 identical interface; ADR-P5.1 model_view/reference split;
ADR-P6-1..7 model pinning + guarded choke point + harness determinism + refusal integrity; ADR-P6.1 answerable grammar
+ containment redefinition + Article XVIII) and add the decisions specific to authoring scenarios and running a matrix.

### ADR-P7-1 — SC-01 is referenced, not re-run

SC-01's canonical cells are the banked P3 (arm_a, naive) and P6.1 (arm_b R0/R1/R2) results. Re-running SC-01 would
risk perturbing an honest banked result and would require touching the frozen headline ledger. The matrix therefore
**references** SC-01 by its `incident_id` and result rows and never regenerates it. Arm A/naive do not use the model,
so their SC-01 cells are valid as-is; Arm B's SC-01 cells were produced under the current (P6.1) answerable grammar, so
they are the canonical Arm B SC-01 cells. This protects both the frozen ledger and the banked headline.

### ADR-P7-2 — new incidents are generated live, then frozen, and are incident-scoped

Each SC-02/03/04 incident is generated against a healthy live lab (so `lab-ready` must reach 0 for generation), then
frozen for its arm evaluations. Each gets its own `incident_id` and paths; the `archive/current` pointer is managed per
incident because after a reset the cluster can re-emit WAL segment names it already emitted with different contents
(the P0 timeline-reuse finding). Reset tiers T0/T1/T2 separate runs. The SC-01 ledger is never touched. Every results
row carries its `incident_id`; incidents are never blended.

### ADR-P7-3 — SC-03 and SC-04 are not single-coordinate scenarios; do not force one

SC-03 deliberately breaks the single-clean-coordinate assumption: restoring before the first destructive DDL discards
the legitimate DML committed during the migration. P7 measures **both** the single-coordinate optimum and the
legitimate DML sacrificed. SC-04 has no single coordinate that removes all corruption while keeping all legitimate
work; ground truth is the corrupted-row set and the earliest malicious commit, scored by precision/recall +
earliest-bounded commit. Forcing either into a single-coordinate pass/fail would misrepresent the result (Article XVIII
spirit). This honest reporting is the selective-recovery future-work hook and the core of the experiment's strongest
scenario, not an inconvenience.

### ADR-P7-4 — stratified plan from measured throughput; under-power is reported, never silent

"Maximum achievable will be attempted" is replaced by explicit per-cell replicate counts derived from a re-measured
full-cycle time (the P0.1 49.335 s figure predated the R005 reset guard and is a floor). Deterministic arms (arm_a,
naive) get one recorded run per cell; arm_b gets K replicates. If the time budget forces cuts, replicate counts on the
easier scenarios are reduced first with a recorded variance caveat; the **SC-04 R0/R1/R2 ablation is fully replicated
and never cut** (descope ladder item 2), and no comparator is ever dropped from a scenario (item 5).

### ADR-P7-5 — the matrix runs unattended; a failed run is a row, not a crash

The orchestrator runs every planned cell with no manual intervention. A run that cannot proceed records an
`outcome="run_failure"` row with a `failure_reason` and the matrix continues; it never silently skips a planned run and
never aborts the batch. `total_rows = total_planned_runs` at completion. The orchestrator is resumable: on restart it
detects recorded cells and does not duplicate them. This is Article VIII (fail loud) in its batch form — a failure is
loud *in the results file* and the run continues.

### ADR-P7-6 — cross-layer recovery is scoped out; SC-02's filesystem track is measured independently

Coordinated filesystem-plus-database recovery (unifying the CoW snapshot boundary with the DB LSN) is the hardest
integration and is scoped out (descope ladder item 4). SC-02 measures the filesystem track independently; the observed
FS<->DB skew and the `checkpoint_gap_seconds` are reported as measured quantities and discussed as a limitation and a
future-work hook, not silently coordinated. This protects the timeline: SC-02 does not depend on solving skew.

### ADR-P7-7 — reuse the P6.1 answerable grammar and containment unchanged

Arm B runs exactly as P6.1 left it: the answerable resolvable-locator grammar (`arm-b-protocol.amendment-1`) and the
containment redefinition (`model-runtime.amendment-1`). P7 does not re-open the grammar or the model pin. If a new
scenario surfaces a grammar inadequacy, that is a superseding amendment with its own ADR and diagnosis (Article XV +
XVIII), never a silent edit.

## No new constitutional article

P0.1, P1.1, P2.1, P3.1, P5.1 and P6.1 each added an article because each was a remediation that surfaced a defect
class (XII test hatches, XIII verification tiers, XIV provenance of record, XV amend-by-supersession, XVI read-only
gates, XVII subject-visible surface, XVIII null root-caused). P7 is a forward build under the eighteen articles in
force. The mandatory-confounder, incident-scoping, unattended-batch and honest-findings rules (ADR-P7-2..6) are strong
ADRs enforced mechanically, not new articles. If P7's own acceptance review finds a defect class the gate missed — the
recurring pattern in this project — that is where Article XIX would come from, not before.

## Task breakdown

| Task | Owns | Serves |
| --- | --- | --- |
| K001 | the two P7 contracts + re-measured throughput + stratified plan + entry gate | FR-1 |
| K002 | SC-02 filesystem scenario: injector + build-and-edit confounder + checkpoint oracle | FR-2 |
| K003 | SC-03 schema/DDL scenario: staged-DDL injector + interleaved DML + first-DDL oracle + trade-off measure | FR-3 |
| K004 | SC-04 stealthy-corruption scenario: randomized-UPDATE injector + high-volume confounder + set/earliest oracle + precision/recall harness | FR-4 |
| K005 | per-scenario R0/R1/R2 build + admissibility + interface parity + guard-clean; SC-01 unchanged re-verify | FR-5, FR-6 |
| K006 | `bin/lab-matrix` unattended orchestrator: reset tiers, incident scoping, one row per run, ledger idempotency | FR-7 |
| K007 | execute the stratified matrix across all cells; complete results file; failures as rows; provenance-blind | FR-8 |
| K008 | honest findings: SC-03 trade-off, SC-04 precision/recall + earliest-bounded, residual-refusal diagnosis | FR-9 (findings) |
| K009 | cross-scenario headline R0-vs-R1-vs-R2 + Arm A/B/naive from machine-readable fields; SC-04 strongest | FR-9 (headline) |
| K010 | `bin/lab-verify-p7` gate; prior-hash re-verify; regression; P7 handoff | FR-10 |

## Sequencing

K001 first (contracts + plan + throughput before any scenario). K002/K003/K004 author the three scenarios and may be
built in any order after K001 (each independent). K005 builds the representations for whichever scenario incidents
exist and re-verifies SC-01 unchanged. K006 builds the orchestrator (needs the scenarios + reset tiers + capture).
K007 executes the matrix (needs K002..K006). K008 computes the honest findings (needs K007's results file). K009
produces the headline (needs K008). K010 gates and runs last.

```
K001 --+-- K002 --+
       +-- K003 --+-- K005 -- K006 -- K007 -- K008 -- K009 -- K010
       +-- K004 --+
```

## Risks

- **A scenario without a real confounder makes detection trivial.** The single highest-consequence scenario-authoring
  risk (roadmap-named). Mitigation: ADR-P7 mandatory-confounder rule + `confounder.overlaps_damage` enforced +
  AC-P7-05 refusal of a confounder-less scenario.
- **SC-03/SC-04 mis-scored as single-coordinate.** Would misrepresent the experiment's most important scenarios.
  Mitigation: ADR-P7-3 + the `set_and_earliest` ground-truth kind + AC-P7-14/AC-P7-15 computing the trade-off and the
  precision/recall from committed fields, with negatives that catch a hidden sacrifice / a wrong malicious set.
- **The matrix blocks or leaves a silent gap on a failed run.** Mitigation: ADR-P7-5 + `outcome="run_failure"` rows +
  `total_rows = total_planned_runs` + resumability (AC-P7-10).
- **Provenance leaks into a scenario's detection path.** Would trivialise the task. Mitigation: ADR-II + the scenario
  schema's provenance rule + `selection_inputs.read_*` false + inject-a-principal negative (AC-P7-13).
- **Cross-incident bleed / ledger desync across resets.** Mitigation: ADR-P7-2 incident scoping + per-incident
  `archive/current` + ledger idempotency + range containment across a reset boundary (AC-P7-09).
- **SC-01 disturbed while generating new incidents.** Mitigation: ADR-P7-1 reference-not-re-run + AC-P7-07
  byte-identical re-verify of SC-01 artefacts and banked results.
- **R0's raw log exceeds the model context on a larger scenario.** That is itself a finding (R0 un-ingestible), not a
  bug to hide; record it and diagnose via Article XVIII (as P6.1 did). Mitigation: AC-P7-16.
- **String LSN comparison in a new injector/oracle.** Mitigation: integer LSN via `bin/lab-coordinate` everywhere; the
  `3/9` vs `3/10` trap covered in the scenario tests.
- **A new scenario forces a frozen-contract deviation.** Mitigation: Article XV — supersede via an amendment file with
  its own ADR; never edit a frozen file, never bury a change in the handoff (the P2 `xid` and P4 sandbox-location
  lessons).

## Carry-forward from prior reviews

- **Re-assert the SC-01 R0/R1/R2 artefact hashes unchanged** (the P6.1-review carry-forward): the ablation's validity
  depends on the SC-01 representations being byte-identical to their P5/P5.1 close. Implemented in K005/AC-P7-07.
- **Re-measure the full-cycle time before building the sample plan** (the P0.1/P1 carry-forward): the 49.335 s figure
  predated the R005 reset guard. Implemented in K001; it feeds the stratified plan.
- **Fixture drift.** The per-tranche regression fixtures are pinned. P7 adds no ledger schema change and must not
  re-pin a fixture; if a new scenario legitimately needs a new pinned fixture, state why in the handoff (K010).
- **Record any sensible substitution as an amendment, not a buried note (Article XV).**
