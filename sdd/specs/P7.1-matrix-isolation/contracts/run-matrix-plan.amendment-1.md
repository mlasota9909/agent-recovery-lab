# Amendment 1 to run-matrix-plan (Article XV supersession)

**Supersedes:** the clauses of the FROZEN `sdd/specs/P7-scenario-matrix/contracts/run-matrix-plan.md` named below.
The original file is **byte-identical**; its P7 hash (`4665066d…`) must re-verify. This amendment is frozen at L004
close with its own hash recorded in `logs/review/L004/`.

## A1. Why

The P7 matrix satisfied `total_rows == total_planned_runs` (51/51) over a run in which 34 SC-03/SC-04 cells were
`run_failure` (shared-pool snapshot destruction) and were then stripped so completeness stayed green, and in which
SC-02/03/04 determinations were scored `restore_verdict=stub` against archive-resolved coordinates. Completeness was
reported without validity, and units that failed for infrastructural reasons were removed rather than superseded. This
amendment corrects the reporting and the resolution path to what Article XIX requires.

## A2. Superseded clause — coordinate resolution

- **Was:** re-run/matrix cells could resolve coordinates from the frozen archive `snapshots.json`
  (`LAB_P7_HOST_COORD=1`, `resolved_by: snapshot_first`), reporting `skew_ms: 0`.
- **Now:** a matrix cell for an incident that has a **live isolated cluster** (per `incident-isolation.md`) MUST
  resolve coordinates live (`resolved_by: live_heartbeat`) with a measured `skew_ms`. The `snapshot_first` path is
  retained **only** for the already-written banked SC-01 rows and any incident whose cluster genuinely cannot be
  brought up (which is then a superseded/blocked cell, not a determination).

## A3. Superseded clause — completeness reporting

- **Was:** the completeness check asserted `total_rows == total_planned_runs`.
- **Now:** completeness (`total_rows == total_planned_runs`) MUST be reported **alongside a validity partition** in
  `matrix-completeness.json`:
  `{determinations, refusals, run_failures, superseded, stub_validations}` with each non-determination carrying a
  machine-readable `cause`. A green completeness count with any undiagnosed `run_failure` or any silently removed cell
  is a gate failure. `total_planned_runs` MUST equal the full design (the SC-03/SC-04 cells are part of the plan, not
  quietly dropped).

## A4. Superseded clause — failed/replaced units

- **Was:** cells that failed for harness/architecture reasons were removed from the results files to preserve the
  count.
- **Now:** a failed or replaced cell is **retained** and marked superseded: the replacement row carries
  `supersedes: <prior_row_id>` and the prior row carries `superseded_by`. Nothing is deleted. The prior P7 stub/hollow
  rows are reconstructed as superseded predecessors of the L004 live rows (or, if the raw prior rows are irrecoverable,
  a `superseded_manifest.json` records their prior existence and cause). This is the append-only discipline of the
  results-row contract applied across a re-run.

## A5. Superseded clause — validation of new scenarios

- **Was:** SC-02/03/04 determinations were `restore_verdict=stub` for want of an `oracle-manifest.json`.
- **Now:** each single-coordinate scenario (SC-02) MUST carry an `oracle-manifest.json` and be scored through the
  unchanged P4 restore+validate path (`restore_verdict` in the P4 verdict set, never `stub`). Set-and-earliest
  scenarios (SC-03, SC-04) are scored by the L003 set-validation path (precision/recall of the malicious set +
  earliest-safe bound), which is a defined non-stub verdict — `stub` is not an acceptable outcome for a cell that ran.

## A6. Unchanged

- The scenario roster, the timing patterns, the mandatory-confounder rule, the results-row schema, the `reset_tier`
  enum, Arm A's 3σ threshold (SC-02's no-3σ `run_failure` remains a genuine reported finding), and every prior frozen
  contract. This amendment changes reporting and resolution discipline, not the experiment's design.
