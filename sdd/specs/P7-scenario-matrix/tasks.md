# Tasks — P7: Scenario expansion and the run matrix

Ordered and dependency-aware. Each task `Knnn` has a work instruction at `work-instructions/WI-Knnn.md` giving the
tier below this list: exact commands, artefacts, tier-labelled acceptance tests, a mandatory negative test, the review
bundle and an operator checklist.

**Run one task per agent invocation. Do not batch.**

Entry conditions apply to every task: `bin/lab-regression` green against pinned fixtures; `bin/lab-ready` can reach
exit 0 for incident generation while the frozen SC-01 headline ledger stays byte-identical; the banked SC-01 results
present; the offline model runtime contained (P6.1 redefinition); and the git working tree clean before producing any
provenance-bearing or results artefact. The confounder is mandatory in every scenario; no arm reads provenance; SC-01
is referenced, never re-run.

## Phase A — Contracts, throughput and the plan

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| K001 | Freeze `scenario-definition.md` + `run-matrix-plan.md`; re-measure full-cycle throughput; record the stratified per-cell plan (SC-04 fully replicated); record the entry gate | — | the two contracts, the plan, the throughput measurement | FR-1, AC-P7-01 |

> K001 fixes what a scenario is and how the matrix is sampled **before** any scenario is authored or any run executed.
> Read both contracts line by line — the mandatory-confounder rule and the `set_and_earliest` ground-truth kind
> (`scenario-definition`) and the unattended one-row-per-run contract (`run-matrix-plan`) are the load-bearing parts.

## Phase B — The three new scenarios

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| K002 | SC-02 filesystem mass-deletion: recursive delete + >=1 overwrite as agent principal; build-and-edit confounder overlapping the damage; oracle = tightest pre-damage checkpoint; `checkpoint_gap_seconds` | K001 | the SC-02 scenario | FR-2, AC-P7-02, AC-P7-05 (SC-02), AC-P7-18 |
| K003 | SC-03 schema damage: staged destructive DDL as agent principal with interleaved legit DML; oracle = LSN before first destructive DDL; `legit_dml_sacrificed`; DDL flagged distinctly | K001 | the SC-03 scenario | FR-3, AC-P7-03, AC-P7-05 (SC-03) |
| K004 | SC-04 stealthy corruption: randomized small UPDATEs to scattered rows as agent principal among high-volume legit updates; oracle = corrupted-row set + earliest malicious commit; precision/recall harness | K001 | the SC-04 scenario | FR-4, AC-P7-04, AC-P7-05 (SC-04) |

> The confounder is mandatory and is the point: SC-02's legitimate file churn, SC-03's interleaved DML and SC-04's
> high-volume legitimate updates are what make each recovery-point problem real. A scenario whose only activity is the
> attack is refused. SC-03 and SC-04 are `set_and_earliest` scenarios — never force them into a single-coordinate
> pass/fail.

## Phase C — Representations and the orchestrator

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| K005 | per-scenario R0/R1/R2 build (reused P5 builder), admissible + interface-parity + guard-clean; re-verify SC-01 artefacts + banked results unchanged | K002, K003, K004 | per-scenario representations | FR-5, FR-6, AC-P7-06, AC-P7-07 |
| K006 | `bin/lab-matrix` — unattended orchestrator: reset tiers, incident scoping, per-incident `archive/current`, one schema-valid row per run, ledger idempotency + range containment per incident, resumable | K005 | `bin/lab-matrix` | FR-7, AC-P7-08, AC-P7-09 |

> K006 is the integrity keystone of the tranche. One schema-valid results row per run, incident-scoped, with ledger
> idempotency holding across reset boundaries. A failed run is a row, not a crash.

## Phase D — Execution, findings and headline

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| K007 | execute the stratified matrix across scenario x timing x arm x representation x replicate; complete results file; failures recorded as rows; every arm-coordinate provenance-blind; scored through unchanged P4 | K006 | the complete results file | FR-8, AC-P7-10, AC-P7-11, AC-P7-12, AC-P7-13 |
| K008 | honest findings: SC-03 single-coordinate optimum + `legit_dml_sacrificed`; SC-04 precision/recall + earliest-bounded commit; residual refusals diagnosed via Article XVIII | K007 | the findings computation | FR-9 (findings), AC-P7-14, AC-P7-15, AC-P7-16 |
| K009 | cross-scenario headline: R0-vs-R1-vs-R2 + Arm A vs Arm B vs naive from machine-readable fields; SC-04 the strongest figure | K008 | the matrix headline | FR-9 (headline), AC-P7-17 |

> K009 is the tranche's reason for existing. The operator will confirm the cross-scenario comparison is computed from
> committed fields (never prose), that SC-04 shows the largest R0-vs-R2 gap, and that a hand-entered figure disagreeing
> with the results file is caught.

## Phase E — Gate

| ID | Task | Depends on | Owns | Serves |
| --- | --- | --- | --- | --- |
| K010 | `bin/lab-verify-p7` tiered + read-only gate; all prior hashes re-verified; regression; P7 handoff | K001..K009 | `bin/lab-verify-p7`, handoff | FR-10, AC-P7-19, AC-P7-20, AC-P7-21 |

## Dependency graph

```
K001 --+-- K002 --+
       +-- K003 --+-- K005 -- K006 -- K007 -- K008 -- K009 -- K010
       +-- K004 --+
```

K002/K003/K004 are independent after K001. K005 needs the scenario incidents; K006 the representations + reset tiers;
K007 the orchestrator; K008 the results file; K009 the findings; K010 runs last.

## Anti-goals for this tranche

Do not, in P7: modify any frozen contract or add a field to results-row / arm-coordinate / representation-interface /
arm-b-protocol / model-runtime; modify the P4 restore+validate path, the representations, the guard, the model pin, or
Arm A / the ranker weights; re-run or disturb the frozen SC-01 headline ledger (reference it); author a scenario
without an overlapping legitimate confounder (Article-II-trivialising); force SC-03 or SC-04 into a single-coordinate
pass/fail; let a failed matrix run block the batch or leave a silent gap; read provenance in any arm; solve coordinated
cross-layer FS+DB recovery (measure SC-02's filesystem track independently and report skew); fine-tune, train, add an
adapter, enable sampling, or make any outbound model call; build the analysis notebook / figures
(that is **P8**). If a task appears to require any of these, it has been misread — record it in `observations.md` and
continue within scope.
