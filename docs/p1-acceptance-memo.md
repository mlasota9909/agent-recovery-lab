# P1 acceptance memo

```json
{
  "restore_stubbed": true,
  "recovery_correctness_claimed": false,
  "oracle_scenario": "SC-01",
  "p2_recommendation": "go",
  "accepted_only_after_p1_1": true,
  "tier_m_passed": 23,
  "tier_a_passed": 1,
  "total_passed": 24,
  "median_generate_s": 75.539,
  "median_evaluate_s": 32.903,
  "planned_incidents": 10,
  "planned_arm_runs": 150,
  "planned_hours": 1.581,
  "completed_arm_runs": 0,
  "completed_incidents": 0,
  "defects": [
    {
      "id": "D1",
      "name": "provenance",
      "closed": true,
      "task": "X002"
    },
    {
      "id": "D2",
      "name": "lab-state",
      "closed": true,
      "task": "X004"
    },
    {
      "id": "D3",
      "name": "planned-vs-completed",
      "closed": true,
      "task": "X005"
    }
  ]
}
```

## Result

P1 instruments are in place: results-row and ledger-integrity contracts frozen, writer/validator, barrier, SC-01 workload and injector, oracle, two-phase harness with stubs, measured cycle times, and this gate.

`bin/lab-verify-p1` is the runner. Per-tier totals are printed separately.

## Cycle time and sample-size headline

Post-reset-guard measurement (`docs/throughput.json`):

- generate-incident median **75.539 s** (n=5)
- evaluate-arm median **32.903 s** under t2 (n=10)
- core **plan** (not yet executed): **10 planned incidents**, **150 planned arm runs**, **1.581 planned hours**
- arithmetic: `planned_arm_runs = planned_incidents × representations × replicates` = 10 × 3 × 5 = 150
- `completed_arm_runs`: **0**; `completed_incidents`: **0**. No experimental arm has been executed. The P1 null run produced stub rows only, now quarantined under `results/fixtures/`.

The inherited 49.335 s figure is not used. See `docs/sample-size-plan.md`.

## Limitation — restore is stubbed

Restore and validation are stubbed in P1 (`restore_verdict: "stub"`, `consistency_verdict: "stub"`). **No claim about recovery correctness is supported.** The loop-closing test that feeds the known-correct coordinate into a real restore is P4.

## Oracle scope

The oracle is SC-01-specific: last legitimate commit LSN strictly before the scripted DELETE. SC-03 and SC-04 do not have that single clean optimum; they need a different definition (earliest malicious commit plus a corrupted-row set). P1 does not build those.

## P1.1 remediation

P1 was accepted only after this remediation (`accepted_only_after_p1_1: true`). Three defects are closed: D1 provenance (`harness_commit` is HEAD at production with dirty-tree refusal), D2 lab-state (`bin/lab-ready` plus the slot-recovery runbook), D3 planned-vs-completed (`planned_*` vs `completed_arm_runs: 0`).

## P2 go/no-go

`p2_recommendation` is **not** a hardcoded sentence. It is set from `bin/lab-ready` (go iff exit 0). P2's entry condition is that gate (ADR-P1.1-4). The ledger schema P2 must not deviate from is wal2json JSONL already stored as `evidence/<scenario>/<incident>/db.jsonl`, with per-incident LSN idempotency and open/close containment as frozen in `contracts/ledger-integrity.md`. P2 collectors attach files beside that stream; they do not rewrite it.

P0 `bin/lab-verify` remains the substrate gate (18/18). P1 contracts hash-match W002; P0 contracts hash-match R007.

## P2 acceptance (appended 2026-08-21)

P2 capture collectors are complete: frozen `capture-completeness.md`, `lab-capture` orchestration, LSN-anchored snapshots, `fs_diff`/`fs_hashes`, DB before-images and DDL, DuckDB `lab-query`, 500-op `lab-capture-workload`, `lab-ledger-account` **ops=500 mapped=500 gaps=0 duplicates=0**, slot dropped at teardown then restored via t2. Gate: `bin/lab-verify-p2`. P3 may build analytics (Arm A) and representations (Arm B) against a ledger that has passed reconciliation; P3 must not read `principal`. See `docs/P2-architecture-handoff.md`.

