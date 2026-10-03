# Database-level replication records

Kept for reference (see `records/history/README.md`). The experiment of record is `records/experiment/`.

The mass-deletion incident (SC-01) run again in the rebuilt lab through
`run/optional/sc01-replication.sh`: one new incident, the Primary Sweep's three models,
R0/R1/R2 and five repeats (45 calls), temperature 0, top-p 1, seed 42, 8,192 output
tokens, the revised answer grammar of the Rule-Repair Phase, and database verdicts (v1).
Its analysis plan is `run/optional/sc01-analysis-plan.md`.

| Folder | Contents |
| --- | --- |
| `frozen-hashes.json` | The freeze (25 files, 45 planned units), committed before the first model call |
| `evidence/` | Incident `SC-01_20260929T213925Z`: incident record, snapshots, decoded log, oracle, workload manifest, analytics |
| `run/` | Gate, inputs (model views and prompts), controls, per-unit journals, stage logs, preflight |
| `results/` | 45 study rows and 2 comparator rows |
| `analysis/` | Stage 70 tables |
| `retired/` | Two unfrozen attempts retired before any model call, with their reasons and evidence |
| `rehearsals/` | Three dry runs of stages 20 and 30, with notes and evidence |

`python3 records/history/SC01-replication/verify.py` checks every frozen hash. The freeze pins
`lib/lab_regrammar.py`, `lib/lab_sc01_replication.py`, `lib/lab_fl_study.py`,
`lib/lab_arm_b_score.py`, `etc/arm-b-prompt.txt`, the analysis plan and the answer-grammar
contracts in place, so those files stay unchanged.

Positions in `workload-manifest.jsonl` were read with `pg_current_wal_lsn()` once after each batch, so they bound
each commit rather than locate it. The decoded log, `db.jsonl`, holds each transaction's commit record. No
credentials are included; paths and private addresses are the reference environment's.
