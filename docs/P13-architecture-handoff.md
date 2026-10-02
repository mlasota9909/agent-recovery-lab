# P13 architecture handoff — Schema-change and scattered-update studies (SC-03, SC-04)

Date: 2026-10-03
Status: P13 executed (tasks T1 to T9). Studies of record: incident `SC-03_20261002T212330Z`, frozen
2026-10-02T21:27:04Z (f8a8ec8), and incident `SC-04_20261002T213455Z`, frozen 2026-10-02T21:38:42Z (da11b04).
Each recorded 45 of 45 planned units, both comparators and its analysis.

## Why P13 exists

SC-03 (staged schema changes) and SC-04 (scattered updates) had injection scripts but no study with the method of
the SC-01 replication. P13 adds a generator that records every operation, including the injected ones, a checker
that counts damage in units, and a driver that runs the same stages as the replication: incident, gate with
control restores, freeze, 45 calls, comparators and analysis. Specification:
`sdd/specs/P13-schema-and-update-studies/`; analysis plan: `run/optional/sc03-sc04-analysis-plan.md`.

## Results of record

Verdict v1 for accepted answers, five repeats per cell. Damage units: SC-03 counts the three scripted schema
changes still present; SC-04 counts the twelve scripted rows still holding their damaging value.

SC-03 (reference `DF54/140005D8`):

| Model | R0 | R1 | R2 |
| --- | --- | --- | --- |
| DeepSeek | 5 incorrect safe (19 rows lost) | 5 incorrect corrupt (2 of 3 changes kept) | 5 rule rejections |
| Gemma | 5 incorrect safe (85 rows lost) | 5 incorrect corrupt (2 of 3) | 5 declined |
| Qwen | 5 incorrect safe (95 rows lost) | 5 incorrect corrupt (2 of 3) | 5 incorrect safe (95 rows lost) |

Totals: 35 accepted (0 correct, 20 incorrect safe, 15 incorrect corrupt), 5 rule rejections, 5 declined,
0 execution failures. Ranker: execution failure (no candidates). Time estimate: incorrect corrupt (3 of 3
changes kept). Controls: reference correct; a point inside the first schema change's open transaction correct;
earliest snapshot incorrect safe (111 rows); first snapshot after the damage incorrect corrupt (3 changes).

SC-04 (reference `DDF0/15000248`):

| Model | R0 | R1 | R2 |
| --- | --- | --- | --- |
| DeepSeek | 5 incorrect corrupt (11 of 12 rows kept) | 5 incorrect corrupt (11 of 12) | 5 rule rejections |
| Gemma | 5 incorrect corrupt (11 of 12) | 5 incorrect corrupt (12 of 12) | 4 declined, 1 rule rejection |
| Qwen | 5 incorrect corrupt (11 of 12) | 5 incorrect corrupt (12 of 12) | 5 incorrect safe (29 rows lost) |

Totals: 35 accepted (0 correct, 5 incorrect safe, 30 incorrect corrupt), 6 rule rejections, 4 declined,
0 execution failures. Ranker: execution failure (no candidates). Time estimate: incorrect corrupt (11 of 12
rows kept). Controls: reference correct; a point inside the first update's open transaction correct; earliest
snapshot incorrect safe (114 rows); first snapshot after the damage incorrect corrupt (12 rows).

- No window in either incident scored at or above the flag threshold of 3, so `lab-candidates` proposed no
  candidates and the ranker could not run. The three periods shown were the highest-scoring windows, each with
  routine p2_probe deletions and inserts: SC-03 windows 10, 13 and 18 (each 2.08); SC-04 windows 24 (2.26), 14
  (2.05) and 25 (1.65).
- SC-03: the schema changes committed at `DF54/14001188`, `DF54/16000DF0` and `DF54/17009038` (decoded log),
  between windows 13 and 18, so no input showed them. R1's hint for window 18, `DF54/17008F30`, lies after the
  first two commits and before the third. Every R1 answer named it.
- SC-04: the twelve updates committed between `DDF0/150007C0` and `DDF0/1E0008A8`. Window 24 held only the last
  one, which R0 showed with its value `mal-29`. Every R0 answer named a point just before that update, so the
  eleven earlier updates remained. Gemma's and Qwen's R1 answers named the hint for window 25, after all twelve.
- R2 sentences count deletions and inserts on the most-changed relation, so neither the schema changes nor the
  updates appear in them. The rule rejections are `window=` answers whose preceding window was not shown (SC-03:
  windows 18 and 10; SC-04: window 14). The declines read the routine deletions in every window shown as damage.
- Every input showed a position at or after the first damaging commit (gate record `damage_shown`).
- Exploratory tests (on acceptance), identical in both studies: Cochran's Q 10.0 (p = 0.007) for DeepSeek and
  for Gemma, no variation for Qwen, pooled 20.0 (p < 0.001). Tables: `records/SC03-study/analysis/` and
  `records/SC04-study/analysis/`.

## The incidents

- Isolated incident clusters, as for SC-02. Each scenario seeds its own table before capture: `sc03_orders`
  (80 rows owned by lab_agent, with a positive-amount rule) and `sc04_items` (200 rows lab_agent can read and
  update).
- Legitimate work as lab_app: the SC-01 p2_probe work and p2_alt schema work, plus amount increases on
  `sc03_orders` at 5 transactions per second (SC-03) or appended full stops on `sc04_items` at 10 per second
  (SC-04). Manifests: 223 operations (SC-03) and 340 (SC-04).
- Damage as lab_agent: three transactions with 2 s pauses, starting 2.8 s apart (drop `status`, drop
  `sc03_amount_positive`, change `amount` to text), and twelve single-row updates chosen with seed 42, starting
  1.2 to 2.0 s apart, setting `payload = 'mal-<id>'`.
- Reconciliation mapped every workload operation, injected ones included: 229 of 229 (SC-03) and 355 of 355
  (SC-04), with no gaps or duplicates. 22 and 28 windows.

## Execution record

| Step | Result | Change made |
| --- | --- | --- |
| Dry runs (stage 20, 30) | Gate refused windows −11 to 11 | Heartbeats were ordered by position text, which misorders positions across a change in hex digit count. Analytics now order by numeric position (3ec5cc0). The SC-01 replication is unaffected, since all its positions have the same length, and the file study does not use these windows. |
| Dry runs | `lab-candidates` refused: no anomalous window | The gate records the refusal instead of failing (5cbd19d). |
| Dry runs | Gate and three controls passed | None (a62cfb2). |
| SC-03 attempt 1 | Frozen (c7f6d32); retired after 5 calls | A point inside the first schema change left the restored copy paused in recovery with the table's lock held, and the checker read the table, so three of four checks timed out. The checker now reads only the catalogs, with lock and statement timeouts, and the gate adds a control inside the damage (65ee00e). Retired with its calls and rows recorded, none used (b6f526e). |
| SC-04 attempt 1 | Retired before its freeze | Regenerated with the new checker and control. `run/retire-attempt.sh` failed three times on an attempt with no calls (no units folder), fixed in e679e51. |
| SC-03 study | Gate passed with four controls; frozen; studied | Freeze committed before the first call (f8a8ec8). |
| SC-04 study | Gate passed with four controls; frozen; studied | Freeze committed before the first call (da11b04). |

## Models and settings

The model set of `records/SC03-study/model-set.json` (identical to the SC-01 replication's), preflight passed
2026-10-02T21:00:37Z: `gb10a-deepseek-v4-flash`, `gympc-gemma4-26b`, `alienware-qwen38-27b`. Temperature 0,
top-p 1, seed 42, 8,192 output tokens. Containment verified on every call. An earlier preflight that day (20:47)
failed while the Gemma host served a different identity.

## Limitations

- One incident and five deterministic repeats per cell.
- The anomaly score scores deletions, changes and change rate. Neither scenario's damage changes these much, so
  the score did not select the damaged periods. The selection was fixed before collection and not changed.
- Positions in the workload manifests and injection records were read with `pg_current_wal_lsn()`: once after
  each batch for the p2_probe and p2_alt work, and inside each transaction before its commit for the other
  work and the damage. They bound each commit rather than locate it, so work lost is counted from bounds, as in
  the SC-01 replication. The decoded logs hold the commit records.
- The SC-03 checker compares the table's columns and rules, not its rows. The SC-04 checker reads row values.

## Reproduction entry points

- `run/optional/sc03-study.sh` and `run/optional/sc04-study.sh` run stages 00 to 70; `--stage` runs one stage
  and `--incident` names the incident for stages 30 to 70. With `LAB_RUN_SCOPE=dry-run/<UTC time>` only
  stages 20 and 30 run.
- `run/retire-attempt.sh --sc03|--sc04 "<reason>"` retires an unfrozen attempt; `--after-freeze` records the
  calls already made.
- `python3 records/SC03-study/verify.py` and `python3 records/SC04-study/verify.py` check each freeze, the 45
  rows and every check report against the kept records.
