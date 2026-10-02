# Scattered-update study records (SC-04)

The scattered-update incident (SC-04) run in the rebuilt lab through `run/optional/sc04-study.sh`, with the method
of the SC-01 replication: one incident, the three models of `model-set.json`, R0/R1/R2 and five repeats (45 calls),
temperature 0, top-p 1, seed 42, 8,192 output tokens, the revised answer grammar and database verdicts (v1). The
specification is `sdd/specs/P13-schema-and-update-studies/` and the analysis plan is
`run/optional/sc03-sc04-analysis-plan.md`.

| Folder | Contents |
| --- | --- |
| `frozen-hashes.json` | The freeze (28 files, 45 planned units), committed before the first model call |
| `evidence/` | Incident `SC-04_20261002T213455Z`: incident record, snapshots, decoded log, injection record, reference, workload record and manifest, analytics |
| `run/` | Gate with its four control restores, inputs (model views and prompts), per-unit and comparator journals, stage logs, the passing preflight and both preflight logs of 2 October 2026 |
| `checks/` | The restore report and checks of each of the ten points restored: five distinct answer points, the time estimate and the four controls |
| `results/` | 45 study rows and 2 comparator rows |
| `analysis/` | Stage 70 tables |
| `rehearsals/` | The dry run of stages 20 and 30 (scope `dry-run/20261002T203614Z`), with its evidence and control checks |
| `retired/` | Attempt `SC-04_20261002T205153Z`, retired before its freeze and before any model call, to regenerate with the lock-safe checker and the inside-damage control: its note, logs, evidence and gate checks |

`python3 records/SC04-study/verify.py` checks every frozen hash, the 45 study rows and the hash of every check
report that a row or control names. The freeze pins `lib/lab_dbscen_study.py`, `lib/lab_generate_dbscen.py`,
`lib/lab_validate_dbscen.py`, the analysis plan, the prompt and the answer-grammar contracts in place, so those
files stay unchanged.

No window scored at or above the flag threshold of 3, so `lab-candidates` proposed no candidates and the ranker's
comparator row records an execution failure. The gate records the same.

Positions in `workload-manifest.jsonl` and `injection.json` were read with `pg_current_wal_lsn()`: once after
each batch for the p2_probe and p2_alt work, and inside each transaction before its commit for the sc04_items
work and the damaging updates. They bound each commit rather than locate it. The decoded log, `db.jsonl`, holds each
transaction's commit record. No credentials are included; paths and private addresses are the reference
environment's.
