# P12 — Tasks

| ID | Task | Depends on | Output | Check |
|---|---|---|---|---|
| A | Portability: repository-relative paths, `etc/lab.env` template plus ignored `etc/lab.local.env`, parameterised VM, devices, ports and gateway; generated WAL-receiver key line; output folders renamed | - | code, `etc/` | AC-1; unit tests pass from a second clone |
| B | Provisioning: host prerequisites check, VM creation from the cloud image, guest and host configuration in P0 order, P0 acceptance as health check | A | `provision/` | AC-2 |
| C | File capture: 2-second recorded snapshots (one writer, collision-free, merged records), diff and hash per snapshot, failure stops the incident, path-bearing file operation records, exact C-7, checker reads the three-column format | A | code, tests | AC-3, AC-7 |
| D | File-level pipeline: intervals and anomaly score, input constructions, prompt wrapper, answer-reading rules, reference and damage manifest, restore to snapshot, checks and verdict v2, ranker and time estimate, controls | C | code, tests, contracts | AC-5, AC-6 |
| E | Run-through: `run/` stages (preflight, incident, incident gate, inputs, freeze, study, comparators, restores, analysis, tables) and `run/all.sh` from provisioning to tables | B, D | `run/` | AC-8, AC-9, AC-10 |
| F | Execute: provision the VM, dry-run incident, fresh incident, author review (tier A), freeze, study, analysis, handoff | E | records, `docs/P12-architecture-handoff.md` | AC-2 to AC-11 |

Work instructions for each task: `work-instructions/WI-P12-<ID>.md`.
