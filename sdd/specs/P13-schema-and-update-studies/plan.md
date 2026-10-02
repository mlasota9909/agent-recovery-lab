# P13 — Plan and decisions

## ADR-1 One method for all four scenarios
SC-03 and SC-04 reuse, unchanged: `lab-analytics`, `lab-anomaly`, `lab-candidates`, `lab-repr-r0/r1/r2`,
`lab-repr-modelview` (PB-6, top three), the model-view guard, `lab-arm-b-prompt` with `etc/arm-b-prompt.txt`, the
revised answer grammar through `database_answer`, `collect_unit`, the model set, the decoding settings (temperature 0,
top-p 1, seed 42, 8,192 tokens) and five repeats. The SC-01 and SC-02 drivers are not edited; the new driver
`lib/lab_dbscen_study.py` imports what it reuses.

## ADR-2 Generator
`lib/lab_generate_dbscen.py` uses the `lab-generate-p7` isolation, capture, snapshot, file-evidence and
reconciliation steps (`freeze_common`) and the SC-01 settings (`etc/scenarios/sc01.env`: 10 s baseline, 4 s after
the injection, 2 s windows, p2_probe workload at 8 transactions per second with seed 7, the legitimate structural
changes). The scenario module seeds its table before the open snapshot and runs its own legitimate loop (SC-03:
amount increases at 5 per second; SC-04: payload appends at 10 per second) and the injection. `lab-generate-p7` is
not edited, so the file study's generator is unchanged.

## ADR-3 Complete workload record
Injected operations are written to `workload.jsonl` as SC-01's are. SC-03: action ALTER, command tag ALTER TABLE,
object `public.sc03_orders`. SC-04: action U, table `sc04_items`, row key. Reconciliation (`map_ops`) then maps the
damage exactly once or reports a gap, and `load_blind_events` includes it in the evidence.

## ADR-4 Reference
`lsn_before` of the first damaging statement, resolved with `lab-coordinate`. `oracle.json` holds the coordinate, the
first damaging commit and the damage manifest; `oracle-manifest.json` holds `optimum_lsn` for the work-lost count.

## ADR-5 Gate checks
After reconciliation the gate requires every injected transaction among the evidence events. After `lab-analytics`
it refuses windows that are negative, out of order or longer than 4 seconds. After the inputs are built it refuses an
empty input. It records, without acting on it, whether each input shows a position at or after the first damaging
commit.

## ADR-6 Checker
`lib/lab_validate_dbscen.py` reads the sandbox that `lab-restore` creates and writes `validation.json` in the SC-01
format, so `lab-verdict` assigns verdict v1 with SC-01's rules. Damage units: SC-03, each scripted schema change
present (status column dropped, positive-amount rule dropped, amount type changed); SC-04, each scripted row whose
payload still begins with its damaging value. Work lost and the file comparison are `lab_validate.py`'s.

## ADR-7 Records
Results: `results/sc03-study-<incident>.jsonl`, `results/sc03-comparators-<incident>.jsonl` (and sc04). Run logs and
units: `logs/run/<incident>/sc03/` (and sc04). Analysis: `analysis-out/sc03/<incident>/` (and sc04). After each run
the records are copied to `records/SC03-study/` and `records/SC04-study/` with `verify.py`, as for SC-01.
