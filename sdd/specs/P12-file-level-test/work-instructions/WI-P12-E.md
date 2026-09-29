# WI-P12-E — Run-through scripts

Goal: `run/all.sh` takes a host with libvirt and the model gateway from nothing to the final tables of the file-level
test, and every stage can be run alone. Read the P12 spec (FR-9, FR-10) and plan (ADR-11, ADR-12). Depends on
WI-P12-B (provision/) and WI-P12-D (file-level pipeline).

## Stages (`run/NN-name.sh`, each `set -euo pipefail`, repository root from its own location, a log under `logs/run/`)
1. `00-provision.sh`: `provision/all.sh` (skipped with a note if the health check already passes).
2. `10-preflight.sh`: model gateway reachable; each model's identity digest (served id, root, maximum length from the
   backend addresses in `etc/lab.local.env`) equals the recorded digest in `runtime/p9-model-set.json`; containment
   check per model (existing `lab-p9-verify-models` logic, writing only under `logs/run/`); lab health (`lab-ready`
   for the main cluster is not required; the incident path creates its own cluster and slot).
3. `20-incident.sh --scenario SC-02`: generate a fresh isolated incident with the fixed generator; print the incident
   id; refuse if an incident is already open.
4. `30-incident-gate.sh <incident>`: spec AC-3 to AC-6 on the incident (captured differences and fingerprints complete,
   exact C-7 at both levels, inputs contain file changes, guard passes, controls give the expected verdicts); stop on
   any failure. Writes `logs/run/<incident>/gate.json`.
5. `40-freeze.sh <incident>`: write `contracts/frozen-hashes.json` over the prompt wrapper, answer rules, checks,
   analysis plan, the three built inputs and the model set; refuse to overwrite an existing freeze.
6. `50-study.sh <incident>`: three models × three inputs × five repeats with the ADR-11 settings; for every reply,
   the answer-reading rules and, if accepted, the check (restore reuse allowed); append one record per unit to
   `results/fl-study-runs.jsonl`; resumable (skips units already recorded); refuses to run without a freeze.
7. `60-comparators.sh <incident>`: ranker and time estimate, each checked; records in `results/fl-comparators.jsonl`.
8. `70-analysis.sh`: the frozen analysis plan over the result files; tables as CSV and Markdown under
   `analysis-out/fl/`; a summary JSON with every count.
9. `all.sh`: stages 00 to 70 in order; stops at the first failure; one top-level log.
Also generalise the Primary Sweep driver so the database-level study can be run on a named incident with
`run/optional/sc01-replication.sh` (same stages for SC-01 with the database-level inputs and the revised rules); not
executed by `all.sh`.

## Site-specific values
Every value that depends on the environment (VM name, VM IP address, SSH user and target, libvirt network and
storage pool, guest device names, PostgreSQL ports, host archive user, model gateway URL and API key variable,
each model backend URL and served model name, DNS names used anywhere) must come from `etc/lab.local.env` and be
listed in one table in `README.md` (key, meaning, value in the reference environment, how to find the value in a
new environment). No script may contain such a value. `run/10-preflight.sh` prints the resolved values at start.

## Documentation
`README.md` at the repository root: what the experiment is (neutral, factual), prerequisites (host, libvirt, model
gateway and the three served models), how to configure `etc/lab.local.env`, how to run `run/all.sh`, what each stage
writes, how long each stage takes, and how to tear down (`provision/99-destroy-vm.sh --yes`).

## Do not
- Do not run the stages. Do not contact the network, a VM, PostgreSQL, ZFS, libvirt or the model gateway. Do not
  create commits. Do not modify files outside this repository. Do not mention tools, assistants or the origin of the
  changes in any file, comment or message.

## Report
Stage list with inputs and outputs, resumability behaviour, and anything that needs live confirmation.
