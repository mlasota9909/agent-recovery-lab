# The experiment

The kept records of one run of `run/experiment.sh` from a fresh clone at commit 633952f, on one VM (reclab06): the
file-deletion study (SC-02), then the row-deletion (SC-01), schema-change (SC-03) and row-update (SC-04) studies.

```bash
python3 records/experiment/verify.py
```

checks the records against each study's freeze. It needs no VM, model or network.

| Path | Contents |
| --- | --- |
| `model-set.json` | The three models' served identities, recorded before the first study |
| `logs/` | The provisioning log, the log of every run stage and the restore command logs |
| `SC-0N/frozen-hashes.json` | The study's freeze, written before its first model call |
| `SC-0N/evidence/<incident>/` | The captured incident evidence |
| `SC-0N/run/<incident>/` | The gate and controls, the three inputs and prompts, and the record of every call |
| `SC-0N/checks/<incident>/` | The check report of every restored point |
| `SC-0N/results/` | 45 result rows and 2 comparator rows |
| `SC-0N/analysis/` | The stage-70 analysis tables |

No capture was refused in this run, so it has no retired attempts. Earlier runs are in `records/history/`.

The archived WAL and the VM's snapshots are not kept; they are needed only to repeat a restore. Paths inside the
records are those of the fresh clone that produced them; `verify.py` maps them to this folder.
