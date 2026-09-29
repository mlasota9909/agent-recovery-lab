# P7 architecture handoff

P7 expands the experiment from one frozen SC-01 headline to a stratified matrix across
SC-02 (filesystem mass deletion; Naihin et al. 2023), SC-03 (staged destructive DDL;
Garcia-Molina & Salem 1987) and SC-04 (stealthy randomized updates; Cemri et al. 2025,
Greshake et al. 2023). SC-01 is referenced, never re-run. Eighteen articles remain in force;
P7 adds none. Article XIX would come from a later review if a new class surfaces.

## Throughput and plan

Re-measured generate_incident mean 63.389 s;
evaluate_arm_t2 mean 232.75550234733964 s.
K=5; total_planned_runs=51.
The P0.1 49.335 s figure was not used as the budget.

## Matrix completeness

total_rows=51 total_planned_runs=51
partition={"determinations": 25, "refusals": 25, "run_failures": 1}.

## SC-02 filesystem track

checkpoint_gap_seconds=2.5579779148101807; fs_db_skew_ms=2718.
Coordinated FS+DB recovery was not attempted (ADR-P7-6).

## SC-03 trade-off

single_coord_optimum_lsn=5/FF000000;
legit_dml_sacrificed=9.

## SC-04 strongest figure

{
  "bytes_ratio_r2_over_r0": 1.3754693366708386,
  "evidence_bytes_r0": 799,
  "evidence_bytes_r2": 1099,
  "gap": 0.95,
  "r0_metric": 0.0,
  "r2_metric": 0.95,
  "strongest_figure": true,
  "token_r0": 198,
  "token_r2": 302,
  "token_ratio_r2_over_r0": 1.5252525252525253
}

## Residual refusals

n_refusals=25; n_diagnosed=25; bare_null=false.
Diagnoses: logs/review/K008/refusal-diagnosis.json.

## Host-side evaluate

Live T2 `zfs rollback -r` on shared DS_PARENT destroys snapshots newer than the target (T012).
SC-02 T2 removed SC-03/SC-04 ZFS snapshots, so SC-03/SC-04 (and subsequent) cells resolve coordinates
from archive snapshots.json with victim_rollback=false. `reset_tier` remains `t2` (schema enum).
P4 restore+validate is unchanged; it is skipped when `oracle-manifest.json` is absent (new scenarios).

## P8

P8 builds the analysis notebook and figures from the complete results file.

## Addendum

Operational challenges and deviations (T2 sibling-snapshot destruction, host-side
evaluate, P4 skip, Article XIV, ledger windowing, gate pins):
`docs/P7-architecture-handoff.addendum.md`.
