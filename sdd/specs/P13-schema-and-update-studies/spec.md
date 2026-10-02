# P13 — Specification: Schema-Change and Scattered-Update Studies

## Problem

The lab defines four scenarios. SC-01 (mass deletion) and SC-02 (file deletion with an overwrite) have studies in this
repository, each with a driver, run script, frozen design and records. SC-03 (staged schema changes) and SC-04
(scattered small updates) have scenario definitions (`scenarios/sc03`, `scenarios/sc04`) and modules
(`lib/lab_sc03.py`, `lib/lab_sc04.py`) but no study: no driver, run script, checks or records, and their tables do not
exist on the lab VM.

Their earlier runs, made with `lab-generate-p7` before the lab was rebuilt, were not valid tests. Verified on those
runs' records:

| Stage | Defect |
|---|---|
| Workload record | `lab_generate_p7.py` writes `workload.jsonl` from the legitimate operations only. The injected operations are recorded in `injection.json` but never added. `load_blind_events` builds the evidence from the mapped workload operations, so neither scenario's damaging operations reached the analytics, the inputs or the ranker. Reconciliation still passed, because unrecorded damaging records are simply left unmapped. |
| Windows | In the scattered-update incident the analytics windows were numbered from −24 to 4, the input builder put all 275 changes into one window spanning the whole incident, and an empty window scored about 281 million. The three windows shown held no changes, so the Raw Log Excerpts input was empty. |
| Checks | Points were scored from the scripts' records by `lab_validate_set.py`, without a restore. |
| Acceptance | The representation check (K005) tested leaks, interface parity and identical rebuilds, not that an input was non-empty or covered the incident. |

## Objective

Run SC-03 and SC-04 as studies of this lab, each with the same method as the SC-01 replication, fully scripted and
repeatable from a clone:

- the same capture, windows, anomaly score and three-period selection;
- the same three inputs, database prompt and revised answer-reading rules;
- the same three models, decoding settings and five repeats per input (45 calls per study);
- every accepted point restored into an isolated copy and checked against a reference from the scripts' records;
- the same comparators (the fixed-rule ranker and the time estimate) and the same analysis.

If the selected periods do not show a scenario's damage, that is the measured result. The method is not changed to
make the damage visible.

## Functional requirements

- FR-1 Incident generation. `bin/lab-generate-dbscen --scenario SC-03|SC-04` follows the SC-01 generator: isolated
  incident cluster, in-cluster heartbeat, recorded snapshots every 2 seconds, change capture, the p2_probe application
  workload and the legitimate structural changes, file evidence, barrier, decoder stop, ledger window and exact
  reconciliation. The scenario module supplies the table seed (before the open snapshot), its legitimate workload and
  the injection.
- FR-2 Complete workload record. Every scripted operation, legitimate or damaging, is in `workload.jsonl` with the
  fields reconciliation keys on: data changes by transaction, table, action and row key; schema changes by
  transaction, command tag and object. Reconciliation must map every operation exactly once, damaging ones included,
  or the incident stops.
- FR-3 Legitimate work manifest. `workload-manifest.jsonl` lists every legitimate data change (application workload
  and scenario workload) with its commit position, as for SC-01.
- FR-4 Reference. The reference is the position the injection records immediately before its first damaging
  statement, resolved to the incident's recorded coordinates. `oracle.json` holds it with the damage manifest. No
  model, ranker or time estimate sees it.
- FR-5 Gate. Before any model call the gate reconciles the ledger, builds the analytics, anomaly scores, candidates,
  inputs and prompts exactly as for SC-01, and refuses the incident if: the analytics windows are not numbered from
  zero in time order; a window spans more than twice the window length; an input's evidence is empty; or any damaging
  operation is missing from the evidence events. It does not require the selected periods to contain the damage.
- FR-6 Checks. A point is restored with `lab-restore` and compared with the reference restore:
  - SC-03: the damaged table's columns, types and constraints. Each scripted schema change still present in the
    restored copy is one unit of checked damage.
  - SC-04: every row's payload. Each scripted row that still holds its damaging value is one unit of checked damage.
  - Both: legitimate work lost is the legitimate operations in the manifest committed after the point and no later
    than the reference, as for SC-01.
  - Verdict v1: correct (no checked damage, no work lost), incorrect_safe (no checked damage, work lost),
    incorrect_corrupt (checked damage remains), not_recovered (no usable restored copy).
- FR-7 Controls. Before freezing, the reference must be correct, the earliest recorded point incorrect_safe and the
  first recorded point after the damage incorrect_corrupt.
- FR-8 Freeze and study. The design is frozen by fingerprint before the first model call: inputs, prompts, rules,
  checker, driver, model set and analysis plan. Then 45 units, one invocation each, never replaced.
- FR-9 Comparators and analysis. The ranker and the time estimate (approximate incident time plus 20 seconds) are
  checked the same way. The analysis follows `run/optional/sc03-sc04-analysis-plan.md`.
- FR-10 Records. Each study's records are copied to `records/<study>/` with a `verify.py` that recomputes their
  fingerprints against the freeze, as for the other two studies.
- FR-11 Run scripts. `run/optional/sc03-study.sh` and `run/optional/sc04-study.sh` run all stages or one stage,
  refuse to overwrite, and allow the dry-run scope (stages 20 and 30 only).

## Non-goals

- No change to the anomaly score, the period selection, the inputs, the prompt, the answer-reading rules or the
  model set.
- No change to the SC-01 or SC-02 records, their frozen files or their drivers.

## Acceptance

- A dry run of each scenario passes the gate and all three controls.
- Each study records 45 units and both comparators, every accepted point is checked, and the analysis is complete.
- `records/<study>/verify.py` passes on a clone.
- Unit tests for the workload record, the gate checks and the checker run without lab commands.
