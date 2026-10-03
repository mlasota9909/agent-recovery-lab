# P12 run records

Kept for reference (see `records/history/README.md`). The experiment of record is `records/experiment/`.

Verbatim copies of the file-level study's run records, kept with the repository so the
results can be checked without the lab. `docs/P12-architecture-handoff.md` describes the study.

| Folder | Contents |
| --- | --- |
| `study/` | Earlier study, incident `SC-02_20260929T200318Z`: `frozen-hashes.json` (the freeze, first committed before the first model call), `model-set.json` (the frozen model registry), `evidence/` (incident evidence, intervals, inputs, reference, checks), `run/` (preflight, gate, per-unit call, reply, answer and check journals, stage logs), `results/` (45 study rows, 2 comparator rows), `analysis/` (stage 70 tables) |
| `rehearsals/` | Dry runs 1 to 7: stage logs, gate records and each failed rehearsal's `NOTE.txt`, plus the incidents' evidence |
| `reproduction/` | The same study run by `run/all.sh` from a fresh clone on a new VM: the completed incident `SC-02_20260929T210623Z` with its freeze, model set, evidence, run logs, results and analysis, provisioning logs, and the retired attempts with their reasons (`retired/`) |
| `superseded/` | The first study incident (8 s baseline), superseded before the freeze and before any model call |

`python3 records/history/P12/verify.py` checks every hash in both freezes against these copies and the
contracts in `sdd/specs/P12-file-level-test/`.

Not kept here: the archived WAL of each incident (about 0.9 GB for the study) and the VM-side ZFS
snapshots, which are needed only to repeat restores. The records contain the reference
checkout's absolute path and the reference environment's private addresses, which the README
site table also lists. They contain no credentials.

A new clone runs its own independent study: stage 40 writes that checkout's freeze to the
untracked path `sdd/specs/P12-file-level-test/contracts/frozen-hashes.json`.
