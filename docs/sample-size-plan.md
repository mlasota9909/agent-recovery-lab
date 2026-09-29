# Sample-size plan (P1, derived from measured cycle times)

```json
{
  "planned_incidents": 10,
  "planned_arm_runs": 150,
  "planned_hours": 1.581,
  "completed_arm_runs": 0,
  "completed_incidents": 0
}
```

This plan replaces an unquantified sample with numbers taken from `docs/throughput.json` after the P0.1 reset guard. The counts above are a **plan**. No experimental arm has been executed.

## Design space

Damage classes (rows):

| Class | Scenario | What is destroyed |
| --- | --- | --- |
| database data | SC-01 | broad `DELETE` on `orders` during legitimate traffic |
| filesystem | SC-02 | files under the protected dataset |
| schema | SC-03 | `ALTER`/`DROP` of scenario relations |
| stealthy row | SC-04 | quiet `UPDATE` of payload |

Timing patterns (columns):

| Pattern | Meaning |
| --- | --- |
| near-instant | damage lands inside the concurrent legitimate workload (SC-01 default) |
| delayed | extra legitimate work after a quiet gap, then damage |

That is an 8-cell grid. Coverage by tranche:

| Tranche | Cells actually run |
| --- | --- |
| P1 | SC-01 × near-instant only, stub arm, to size the instrument |
| P3 | Arm A (deterministic ranker) on frozen P1/P8 incidents |
| P4 | real restore; does not add cells |
| P5–P6 | Arm B over R0/R1/R2 on the same incidents |
| P8 | remaining damage classes and the delayed timing pattern |

## Core result (the numbers in `throughput.json`)

SC-01 and SC-02 with the full R0/R1/R2 ablation constitute a complete result on their own.

- incident replicates per cell: 5
- cells in the core: 2 damage classes × 1 timing (near-instant) = 2
- `planned_incidents` = 2 × 1 × 5 = **10**
- representations = **3** (R0, R1, R2)
- arm replicates per incident×representation = **5**
- `planned_arm_runs` = 10 × 3 × 5 = **150**
- `completed_incidents` = **0**
- `completed_arm_runs` = **0**

These are projections from the measured cycle time. No experimental arm has yet been executed. The P1 null run is quarantined under `results/fixtures/` and does not count.

Arm A (representation `none`) is one extra evaluate per planned incident (10 planned runs) and is **not** folded into `planned_arm_runs`; the frozen arithmetic for AC-P1-22 is exactly `planned_incidents × representations × replicates`.

## Time budget

Measured post-reset-guard (`measured_post_reset_guard: true`):

| Phase | n | median_s | min_s | max_s | sd_s |
| --- | --- | --- | --- | --- | --- |
| generate-incident | 5 | 75.539 | 74.810 | 76.153 | 0.447 |
| evaluate-arm (t2) | 10 | 32.903 | 32.423 | 33.210 | 0.269 |

Planning uses the **median**:

`planned_hours` = (10 × 75.539 + 150 × 32.903) / 3600 = **1.581 h**

Risk statement uses the **worst case** (max):

`worst_case_hours` = (10 × 76.153 + 150 × 33.210) / 3600 = **1.595 h**

Host load average during measurement was ~1.1–1.9 on 24 CPUs. Concurrent load would reduce throughput; these hours are a floor.

The inherited 49.335 s full-cycle figure implied ~583 cycles in 8 h. A generate+evaluate pair now costs 108.442 s median, so an 8 h window holds ~266 such pairs. The matrix is dominated by arm evaluations at 32.9 s, not by incident generation.

## Full grid if time remains

4 classes × 2 timings × 5 incident replicates = 40 **planned** incidents; 40 × 3 × 5 = 600 **planned** arm runs.

Median cost: (40 × 75.539 + 600 × 32.903) / 3600 ≈ 6.32 h, still inside a working day.

## Descope ladder

Dropped first if the clock runs out:

1. Delayed timing pattern (keep near-instant only).
2. SC-04 stealthy corruption.
3. SC-03 schema damage.

Stop at SC-01 + SC-02 + R0/R1/R2. That is a complete result.

P1 does not run this matrix. It only sizes it.
