# Spec — P7: Scenario expansion and the run matrix

**Feature ID:** P7-scenario-matrix
**Status:** ready for implementation
**Owner:** Maciej Lasota
**Depends on:** P1 (results row, two-phase harness, reset tiers), P2/P2.1 (capture + reconciliation), P3/P3.1 (Arm A,
naive, SC-01 realized, regression), P4 (restore+validate), P5/P5.1 (representations + interface + guard), P6/P6.1 (Arm
B harness under the answerable grammar + containment redefinition + Article XVIII).
**Blocks:** P8 (analysis and figures).

## 1. Purpose

Turn the single-scenario SC-01 result into the experiment. Implement SC-02 (filesystem mass deletion), SC-03 (schema
damage by staged DDL) and SC-04 (stealthy slow corruption) against the existing harness; add the timing-pattern
variants; define a stratified run plan with per-cell replicate counts from **re-measured** throughput; and execute the
whole matrix unattended, appending one schema-valid results row per run. The deliverable is a complete results file
spanning scenario x timing x arm x representation x replicate, and the cross-scenario R0-vs-R1-vs-R2 comparison — with
SC-04 as the strongest evidence that representation, not model size, is what makes recovery-point identification
tractable for a modest model.

P7 adds scenarios and orchestration; it changes nothing upstream. Arm A, the naive comparator, the representations, the
guard, the model pin and the P4 path are all reused unchanged.

## 2. Background — what already exists

P7 is scenario authoring + orchestration over finished, certified infrastructure. Reuse, do not rebuild:

- The SC-01 injector + confounder + oracle (P3), and the banked SC-01 results (P3 arm_a/naive, P6.1 arm_b).
- `bin/lab-rank` (Arm A), the naive comparator (P3); `bin/lab-arm-b` + `-prompt` + `-extract` + `bin/lab-model` (P6,
  under the P6.1 answerable grammar); `bin/lab-repr-*`, `bin/lab-modelview-guard`, `bin/lab-repr-reference` (P5/P5.1);
  the P5 representation builder + F006 admissibility manifests.
- The **unchanged** P4 restore+validate path + 4-level verdict; `bin/lab-coordinate`; the two-phase
  generate-incident/evaluate-arm harness + reset tiers T0/T1/T2 (P0/P1); the capture + reconciliation pipeline
  (P2/P2.1); `bin/lab-ready`, `bin/lab-reset`; `bin/lab-regression`, `bin/lab-gate-readonly-check` (P3.1);
  `bin/lab-diagnose-refusal` (P6.1, the J001 taxonomy).

P7 adds: the two contracts (scenario-definition + run-matrix-plan), the three new scenario definitions with their
injectors/confounders/oracles, the per-scenario representation build, the unattended matrix orchestrator, the
honest-findings computation (SC-03 trade-off, SC-04 precision/recall), the cross-scenario headline, and the gate.

## 3. Scope

### In scope

- Two frozen contracts: `scenario-definition.md` (machine-checkable scenario schema incl. corpus citation and the
  mandatory-confounder rule) and `run-matrix-plan.md` (stratified per-cell replicate counts from re-measured
  throughput; unattended one-row-per-run contract).
- SC-02/03/04 scenario definitions: injector (as agent principal), concurrent legitimate confounder (as app principal,
  overlapping the damage window), and the ground-truth oracle computed from the scripted record.
- Timing-pattern variants (near_instant / slow / randomized) realized in the injectors and recorded per run.
- Per-scenario R0/R1/R2 representations built with the reused P5 builder, each admissible, interface-parity-holding and
  guard-clean.
- `bin/lab-matrix` — the unattended orchestrator: reset tiers between runs, incident-scoped, `archive/current` managed
  per incident, one schema-valid results row per run, ledger idempotency + range containment per incident, resumable.
- Execution of the stratified matrix across all planned cells, producing the complete results file.
- Honest-findings computation: SC-03 single-coordinate optimum + legitimate DML sacrificed; SC-04 precision/recall of
  malicious transactions + earliest correctly-bounded commit; residual refusals/nulls diagnosed via Article XVIII.
- The cross-scenario headline (R0-vs-R1-vs-R2 + Arm A vs Arm B vs naive) from machine-readable fields, SC-04 foremost.
- `bin/lab-verify-p7` tiered read-only gate; prior contract-hash re-verification; regression; the P7 handoff.

### Out of scope

- Any change to a frozen contract, or any new field on results-row / arm-coordinate / representation-interface /
  arm-b-protocol / model-runtime.
- Any modification to the P4 path, the representations, the guard, the model pin, or Arm A / the ranker weights.
- Coordinated cross-layer filesystem-plus-database recovery: SC-02's filesystem track is measured **independently**;
  observed FS<->DB skew is reported as a finding (descope ladder item 4).
- Re-running or disturbing the frozen SC-01 headline ledger; SC-01 is referenced.
- The analysis notebook and figures (that is **P8**).
- Fine-tuning, training, adapters, sampling, or any outbound model call.

## 4. Functional requirements

- **FR-1 Contracts + plan + entry gate.** Both P7 contracts written and hash-frozen. The full-cycle throughput is
  re-measured and the stratified run plan (per-cell replicate counts, total N, SC-04 fully-replicated) is recorded.
  The tranche opens only when `bin/lab-regression` is green, `bin/lab-ready` can reach exit 0 for incident generation,
  the banked SC-01 results are present, and the model runtime is contained (P6.1 redefinition).
- **FR-2 SC-02.** A filesystem mass-deletion/overwrite scenario: a recursive delete plus at least one overwrite as the
  agent principal; a build-and-edit confounder that legitimately creates/modifies/deletes files in the same tree
  throughout (so legitimate deletion is normal); ground-truth optimum = the tightest CoW snapshot/Merkle checkpoint
  before the damage, with the checkpoint-granularity gap recorded as a measured quantity; corpus citation recorded.
- **FR-3 SC-03.** A staged-DDL schema-damage scenario: a sequence of destructive DDL (drop column, alter type, drop
  constraint) spread over time as the agent principal, with legitimate DML committing in between; ground-truth =
  the LSN before the first destructive DDL; the legitimate DML that a single-coordinate restore sacrifices is computed
  and reported (the trade-off); DDL flagged distinctly from DML in the evidence; corpus citation recorded.
- **FR-4 SC-04.** A stealthy-corruption scenario: many small UPDATEs to scattered rows at randomized intervals as the
  agent principal, dispersed among a high volume of legitimate updates; ground-truth = the exact corrupted-row set and
  the earliest malicious commit; a precision/recall harness against the known malicious set; no single coordinate is
  forced; corpus citations recorded.
- **FR-5 Mandatory confounder.** Every scenario has concurrent legitimate activity overlapping the damage window; the
  scenario schema's `confounder.overlaps_damage` must be true; a scenario without it is refused.
- **FR-6 Per-scenario representations.** For each new scenario incident, R0/R1/R2 are built with the reused P5 builder,
  each admissible (F006), interface-parity-holding (identical `model_view` envelope except `content`) and guard-clean
  (no answer/reference/coordinate/provenance); byte-identical rebuild. SC-01 artefacts and banked results re-verify
  unchanged.
- **FR-7 Unattended orchestrator.** `bin/lab-matrix` runs a cell end-to-end with automatic reset tiers, incident
  scoping and `archive/current` management, appending exactly one schema-valid results row per run; ledger idempotency
  and range containment hold per incident; the orchestrator is resumable and never blends incidents.
- **FR-8 Matrix execution.** The full stratified matrix is executed unattended; a run that cannot proceed records an
  `outcome="run_failure"` row and the matrix continues; `total_rows = total_planned_runs`; determinations, refusals
  and failures are accounted; every arm-coordinate has `selection_inputs.read_*` all false.
- **FR-9 Honest findings + headline.** SC-03's single-coordinate optimum and legitimate-DML-sacrificed, and SC-04's
  precision/recall + earliest-bounded commit, are computed from committed fields; residual refusals/nulls are
  root-caused via the Article XVIII taxonomy; the cross-scenario R0-vs-R1-vs-R2 and Arm A/Arm B/naive comparison is
  produced from machine-readable fields with SC-04 as the strongest figure.
- **FR-10 Gate + handoff.** `bin/lab-verify-p7` runs every P7 check with per-tier totals, is read-only over the
  evidence root, re-verifies every prior contract hash unchanged, and `bin/lab-regression` is green; the P7 handoff
  records the plan + measured throughput, the four scenarios + citations, the matrix completeness, the SC-04 result,
  the SC-03 trade-off, the residual-refusal diagnoses, and states P8 does analysis.

## 5. Acceptance criteria

| ID | Tier | Requirement |
| --- | --- | --- |
| AC-P7-01 | M | Both P7 contracts exist, example JSON parses, hash-frozen in `logs/review/K001/`; full-cycle throughput re-measured and recorded; the stratified plan records per-cell replicate counts, `total_planned_runs`, and SC-04 fully-replicated; entry gate recorded (regression green, `lab-ready` can reach 0, banked SC-01 present, model contained) |
| AC-P7-02 | M | SC-02 definition satisfies `scenario-definition.md`; injector performs a recursive delete + >=1 overwrite as the agent principal; the build-and-edit confounder overlaps the damage window; ground-truth optimum = tightest pre-damage checkpoint, computed from the snapshot/LSN record; `checkpoint_gap_seconds` recorded; corpus citation (Naihin 2023) present |
| AC-P7-03 | M | SC-03 definition valid; staged destructive DDL (drop column / alter type / drop constraint) as the agent principal with legitimate DML interleaved; ground-truth = LSN before first destructive DDL; `legit_dml_sacrificed` computed and non-hidden; DDL flagged distinctly from DML in the evidence signature; corpus citation (Garcia-Molina & Salem 1987) present |
| AC-P7-04 | M | SC-04 definition valid; randomized small UPDATEs to scattered rows as the agent principal dispersed among high-volume legitimate updates; ground-truth = exact corrupted-row set + earliest malicious commit; a precision/recall harness against the known set exists; no single coordinate is forced; corpus citations (Cemri 2025; Greshake 2023) present |
| AC-P7-05 | M | The mandatory-confounder rule is enforced: every scenario has concurrent legitimate activity overlapping the damage window (`confounder.overlaps_damage=true`); a scenario definition missing the overlapping confounder is refused |
| AC-P7-06 | M | For each new scenario incident, R0/R1/R2 are built (reused P5 builder), each admissible (F006), interface parity holds (identical `model_view` envelope except `content`), guard-clean (no answer/reference/coordinate/provenance token), byte-identical rebuild |
| AC-P7-07 | M | SC-01 R0/R1/R2 artefacts and banked results (P3 arm_a/naive, P6.1 arm_b) are byte-identical/unchanged; SC-01 is included in the matrix by reference, not re-run; the frozen SC-01 headline ledger is untouched |
| AC-P7-08 | M | `bin/lab-matrix` runs a cell end-to-end with automatic reset tiers, incident scoping and per-incident `archive/current` management, and appends exactly one schema-valid `results-row` per run carrying `scenario_id`/`timing_pattern`/`arm`/`representation`/`incident_id`/`replicate_index` |
| AC-P7-09 | M | Ledger idempotency + range containment hold per generated incident (no LSN twice within an incident; ledger range within incident open/close), including across a reset boundary; the duplicated-LSN-across-reset case is caught |
| AC-P7-10 | M | Unattended execution: the full stratified matrix runs with no manual intervention per run; a run that cannot proceed records an `outcome="run_failure"` row with `failure_reason` and the matrix continues; `total_rows = total_planned_runs`, partitioned into determinations/refusals/failures |
| AC-P7-11 | M | Timing-pattern variants (near_instant/slow/randomized) are realized in the injectors and recorded per row; the plan's per-cell replicate counts are executed and matched (SC-04 ablation fully replicated) |
| AC-P7-12 | M | Arm A (ranker) and naive run on every scenario; Arm B (R0/R1/R2) runs on every scenario through the guarded `model_view`; single-coordinate determinations are scored through the **unchanged** P4 path (P4 gate hash unchanged) |
| AC-P7-13 | M | Provenance-blind selection across all arms: every arm-coordinate has `selection_inputs.read_injection_log=read_oracle_optimum=read_provenance=false`; no principal token in any model input or rationale; the inject-a-principal negative is caught |
| AC-P7-14 | M | SC-03 honest finding: the single-coordinate optimum LSN AND the `legit_dml_sacrificed` by restoring there are computed from committed fields; claiming zero sacrifice when legitimate DML committed in the migration window is caught |
| AC-P7-15 | M | SC-04 honest finding: `malicious_txn_precision`/`recall` against the known malicious set + `earliest_bounded_commit` are computed from committed fields; scoring against a wrong malicious set is caught |
| AC-P7-16 | A | Residual refusals or null cells are root-caused via the J001 / Article XVIII taxonomy from the verbatim completions (asserts on the machine-readable diagnosis fields), never reported as a bare finding |
| AC-P7-17 | M | The cross-scenario headline (R0-vs-R1-vs-R2 + Arm A vs Arm B vs naive) is produced from machine-readable fields with SC-04 as the strongest figure; a hand-entered figure disagreeing with the results file is caught |
| AC-P7-18 | M | Cross-layer scope honoured: SC-02's filesystem track is measured independently; observed FS<->DB skew is reported as a quantity; `checkpoint_gap_seconds` reported (not silently coordinated) |
| AC-P7-19 | M | `bin/lab-verify-p7` reports every criterion with per-tier totals printed separately, exit 0, and is read-only over the evidence root (proven by `bin/lab-gate-readonly-check`) |
| AC-P7-20 | M | All prior gates green via regression; every prior contract hash unchanged incl. `capture-completeness.md`, `representation-interface.md`(+amendment-1), `arm-b-protocol.md`(+amendment-1), `model-runtime.md`(+amendment-1) byte-identical; `bin/lab-regression` green against pinned fixtures |
| AC-P7-21 | A | The P7 handoff records the plan + measured throughput, the four scenarios + corpus citations, the matrix completeness, the SC-04 cross-representation result, the SC-03 trade-off, the residual-refusal diagnoses, and states P8 does analysis (asserted on machine-readable fields; anti-goal-inversion guarded) |

Nineteen of twenty-one criteria are tier M. The two tier A criteria are the residual-refusal diagnosis record
(AC-P7-16) and the handoff record (AC-P7-21), both asserting on machine-readable fields, per Article XIII.

## 6. Definition of done

`bin/lab-verify-p7` green with per-tier totals and proven read-only; both P7 contracts frozen; the full-cycle
throughput re-measured and the stratified plan recorded with SC-04 fully replicated; SC-02/03/04 defined with
mandatory overlapping confounders, computed ground truth and corpus citations; per-scenario R0/R1/R2 built admissible,
interface-parity-holding and guard-clean; SC-01 artefacts and banked results unchanged and referenced; the unattended
matrix executed with one schema-valid row per run, failures recorded as rows, ledger idempotency per incident, and
`total_rows = total_planned_runs`; every arm-coordinate provenance-blind and scored through the unchanged P4 path where
applicable; SC-03's trade-off and SC-04's precision/recall + earliest-bounded commit computed from committed fields;
residual refusals root-caused via Article XVIII; the cross-scenario R0-vs-R1-vs-R2 headline produced from
machine-readable fields with SC-04 foremost; all prior gates, regression and contract hashes unchanged; and the P7
handoff written without anti-goal inversion.
