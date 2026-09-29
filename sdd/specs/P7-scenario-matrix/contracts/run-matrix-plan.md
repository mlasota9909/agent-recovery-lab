# FROZEN CONTRACT — Run Matrix Plan (stratified sampling from measured throughput)

**Frozen by:** K001
**Status:** FROZEN — changes only by amendment-through-supersession (Article XV).
**Authority:** Article I (deterministic harness), Article VIII (fail loud / continue), Article XIII (verification
tiers), Article XVIII (null root-caused). Honours `results-row.md` without modification (one row per run).

## 1. Why this contract exists

"Maximum achievable sample will be attempted" is not a plan. This contract replaces it with an
explicit stratified design: named cells, a per-cell replicate count derived from **measured** harness throughput, an
explicit total N, and the rule that under-powered cells report variance rather than being silently dropped. It also
fixes the unattended-execution contract: one schema-valid results row per run, and a run that cannot proceed records a
structured failure row so the matrix never blocks and never leaves a silent gap.

## 2. The design space

A cell is `(scenario, timing_pattern, arm, representation)`:

- `scenario` in {SC-01, SC-02, SC-03, SC-04}
- `timing_pattern` in {near_instant, slow, randomized}, restricted to the variants each scenario legitimately supports
  (SC-01 near_instant; SC-02 near_instant; SC-03 slow; SC-04 randomized — plus any additional timing variant a
  scenario definition declares)
- `arm` in {arm_a, naive, arm_b}
- `representation` in {R0, R1, R2} for `arm_b`; `NA` for `arm_a` and `naive` (they do not read a representation)

Replicates: `arm_a` and `naive` are deterministic, so `replicates = 1` per cell (re-run must reproduce byte-identical;
recorded once). `arm_b` uses `K` replicates per cell (the stochastic subject), `K` fixed here and matching
`arm-b-protocol` R8.

## 3. Per-cell replicate counts — derived from measured throughput, recorded in K001

K001 re-measures the full generate+capture+reconcile+evaluate+reset cycle time on the current lab (the P0.1 49.335 s
figure predated the R005 reset guard and is a floor, not a budget — re-measure it). The plan records:

- `measured_cycle_seconds` — the re-measured mean full-cycle time (arm_b evaluation against a frozen incident via T2 is
  cheaper; record both the generate-incident cost and the evaluate-arm cost).
- `time_budget_hours` — the wall-clock budget for the matrix.
- `K` — arm_b replicates per cell (default 5; raised only if the budget permits, lowered only with a recorded variance
  caveat).
- `per_cell` table — for each cell, the planned replicate count and the throughput rationale.
- `total_planned_runs` — the sum; every run appends exactly one results row.

Rule: the **R0/R1/R2 ablation on SC-04 is mandatory and fully replicated** (descope ladder item 2 — without it there
is no contribution). If the budget forces cuts, cut replicate counts on the easier scenarios first and record the
reduced power as a variance caveat; never drop the SC-04 ablation and never drop a comparator (Arm A or naive) from a
scenario.

## 4. SC-01 is included by reference, not re-run

SC-01's canonical cells are the banked P3 (arm_a, naive) and P6.1 (arm_b R0/R1/R2) results. The plan references their
`incident_id` and result rows; it does **not** regenerate the frozen SC-01 headline ledger. If uniform re-scoring is
ever needed it is done read-only against the frozen ledger, never by re-injection.

## 5. Unattended execution contract

- Every run appends exactly one row conforming to the frozen `results-row.md`, carrying `scenario_id`,
  `timing_pattern`, `arm`, `representation`, `incident_id`, `replicate_index`, and the outcome fields.
- A run that cannot proceed (capture failure, reconciliation gap, model runtime unavailable, restore error) records a
  row with `outcome="run_failure"` and a `failure_reason`, then the matrix **continues** to the next run. It never
  silently skips a planned run and never aborts the batch (Article VIII, batch form).
- `total_rows = total_planned_runs` at completion, partitioned into determinations, refusals and run_failures; any
  shortfall is a matrix defect.
- The orchestrator is resumable: on restart it detects cells already recorded and does not duplicate them.
- No manual intervention per run. Reset tiers (T0/T1/T2) between runs are automatic; incident scoping and
  `archive/current` management are automatic.

## 6. Ground-truth and scoring per arm

- `arm_a` and `arm_b` single-coordinate determinations are scored through the **unchanged** P4 restore+validate path
  against the scenario oracle; `naive` is the timestamp baseline scored the same way.
- For `set_and_earliest` scenarios (SC-03, SC-04) the per-scenario metrics of `scenario-definition` §4.2 are computed
  in addition to (SC-03) or instead of (SC-04) a single-coordinate verdict; a single-coordinate pass/fail is never the
  headline for these two.

## 7. Example plan header (illustrative — real values recorded in K001)

```json
{
  "measured_cycle_seconds": {"generate_incident": 61.2, "evaluate_arm_t2": 12.4},
  "time_budget_hours": 8,
  "K": 5,
  "per_cell_example": {"scenario": "SC-04", "timing": "randomized", "arm": "arm_b", "representation": "R2", "replicates": 5, "rationale": "mandatory fully-replicated ablation cell"},
  "total_planned_runs": 0
}
```

## 8. Change control

Frozen at K001, hash-recorded in `logs/review/K001/`. Further change supersedes via `run-matrix-plan.amendment-N.md`
with its own ADR. This file stays byte-identical (Article XV).
