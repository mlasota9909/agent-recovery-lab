# P3 Derived Analytics & Arm A — Architecture Handoff (tranche close)

**Date:** 2026-08-24  
**Status:** P3 **ANALYTICS + ARM A COMPLETE** — SC-01 headline is an honest Arm A win on damaged rows retained (0 vs 200).  
**Gate:** `bin/lab-verify-p3` **TIER M 16/18 · TIER A 1/1 · TOTAL 17/19** (nested prior gates not all green; see §8).  
**Human review:** `sdd/specs/P3-analytics-ranker/checklist.md` Reviewed column still ☐.

Load this file **together with** `docs/P2.1-architecture-handoff.md` (and P2 / P1.1 / P1 / P0.1 / P0). P4 must not restore against an arm coordinate whose `selection_inputs` peek flags are not all `false`.

```json
{
  "analytics_feature_set": [
    "change_burst_density",
    "churn_by_relation",
    "churn_by_path",
    "n_deletes",
    "ddl_flag"
  ],
  "window_s": 2,
  "ranker_version": "p3-rank-1",
  "tie_break": "latest_safe_lsn_int",
  "safe_rule": "lsn_int < first_anomalous_window.lsn_start_int AND anomaly_score < 3",
  "sc01_incident": "SC-01_20260824T091611Z",
  "sc01_results_incident_id": "i_20260824T091611Z_122142",
  "arm_a": {
    "results_arm": "deterministic",
    "lsn": "1/E0000778",
    "lsn_int": 8053065592,
    "snapshot": "s_20260824T091612Z",
    "damage_rows_retained": 0,
    "legit_rows_lost": 48,
    "coord_error_bytes": 16775304,
    "coord_direction": "before"
  },
  "naive": {
    "results_arm": "naive",
    "lsn": "1/E50007A8",
    "lsn_int": 8136951720,
    "snapshot": "s_20260824T091654Z",
    "damage_rows_retained": 200,
    "legit_rows_lost": 0,
    "coord_error_bytes": 67110824,
    "coord_direction": "after",
    "incident_time_error_seconds": 20
  },
  "headline": "arm_a_wins",
  "primary_metric": "damage_rows_retained",
  "provenance_blind": true,
  "selector_reads_injection_log": false,
  "p4": "restore+validation against the chosen coordinate",
  "p5": "builds representations R0/R1/R2",
  "p6": "builds Arm B model harness",
  "anti_goal_inversion": false,
  "capture_completeness_sha256": "59aeaa61281f211046b953a0641de72dc55c3f6cecc7278ee45802d41003d647",
  "lab_verify_p3": "17/19",
  "nested_gates": {
    "lab-verify": "15/18",
    "lab-verify-p1": "crash",
    "lab-verify-p1.1": "crash",
    "lab-verify-p2": "16/18",
    "lab-verify-p2.1": "14/16"
  }
}
```

---

## 1. Where the build stands

```
P0    substrate ............. DONE (18/18 at last P2.1 close of P0 itself)
P0.1  remediation ........... DONE
P1    instruments ........... DONE (nested gate historically crashed on analyse-stub; re-run at D010)
P1.1  remediation ........... DONE (evaluate-arm requires a clean tree, Article XIV)
P2    capture ............... DONE, then found unsound under repeated keys
P2.1  reconciliation ........ DONE — xid bijection; greedy withdrawn
P3    analytics + Arm A ..... THIS FILE
P4    restore + validation .. NEXT — restore against the chosen coordinate; validate vs oracle
P5    representations ....... NEXT AFTER P4 — builds R0 / R1 / R2
P6    Arm B model harness ... NEXT AFTER P5 — modest local model over those representations
```

P3 built **no restore, no representation, no model**. Frozen `capture-completeness.md` was **not** edited. The two P3 contracts (`candidate-coordinate.md`, `arm-coordinate.md`) are hash-frozen in `logs/review/D001/`.

---

## 2. Analytics feature set (window_s = 2)

`bin/lab-analytics` buckets the provenance-blind DuckDB views (`db_changes`, `heartbeats`, `ddl_events`, `fs_diff`) into 2-second windows declared in `etc/scenarios/sc01.env` (`SC01_WINDOW_S=2`). Per window it records:

- `change_burst_density` — changes / window duration
- `churn_by_relation` / `churn_by_path`
- `n_deletes` / `deletes_by_relation`
- `ddl` — true iff the window contains a DDL record

`bin/lab-anomaly` scores each window mean+3σ against the **declared** quiescent baseline in `incident.json` that **predates** injection (ADR-P3-4). On SC-01 the deletion spike is window 15 (201 deletes, `anomaly_score=250.5`); window 0 is quiescent (`score=-0.75`). DDL flags fire on windows 4 and 19 only.

Detection SQL is refused if it names a provenance column. Default views never project `principal`.

---

## 3. Ranker (Arm A) and naive comparator

Weights and the tie-break live in `etc/rank-weights.json`, version **`p3-rank-1`**:

- score = Σ wᵢ · featureᵢ over the frozen candidate feature set
- **tie-break:** latest safe integer LSN (`latest_safe_lsn_int`)
- **safe:** `lsn_int < first_anomalous_window.lsn_start_int` AND `anomaly_score < 3`

P3 `arm=arm_a` is stored on the results row as **`arm=deterministic`** (frozen enum). Mapping onto `chosen_coordinate` (there is no results-row field named `recovery_coordinate`):

| arm-coordinate | results-row |
| --- | --- |
| `lsn_text` | `chosen_coordinate.lsn` |
| `lsn_int` | derived `(high<<32)+low` |
| `wall_clock` | `chosen_coordinate.wall_clock` |
| `snapshot` | `chosen_coordinate.snapshot` |

The naive comparator (`bin/lab-naive`) takes the last checkpoint before `approx_incident_time` plus a **declared, fixed** error `SC01_NAIVE_TIME_ERROR_SECONDS=20`. That parameter was not fitted after seeing Arm A (ADR-P3-3).

---

## 4. SC-01 headline

Incident archive **`SC-01_20260824T091611Z`** (results id `i_20260824T091611Z_122142`). Reconciliation **319/319/0/0**. Probe relation `public.p2_probe`. Consumer was **stopped** on this incident to freeze the ledger; **never** `lab-capture stop` (that drops `lab_slot`).

| arm | results.arm | damage_rows_retained | coord_error_bytes | coord_direction | legit_rows_lost |
| --- | --- | --- | --- | --- | --- |
| Arm A | deterministic | **0** | 16775304 | before | 48 |
| naive | naive | **200** | 67110824 | after | 0 |

Primary metric: damaged rows retained (lower better), tie-break LSN error. **Arm A wins honestly.** Oracle scoring only — P3 does not restore (P4 does).

---

## 5. Provenance-blindness and no-peek

WAL `db.jsonl` records carry `xid` and no `principal` column. Workload `principal` is quarantined to the oracle/scoring path. Re-running analytics → candidates → rank on a principal-stripped ledger copy left Arm A's coordinate **byte-identical**.

A deliberate leak (ranker joined `workload.jsonl` `principal==lab_agent` and preferred the nearest agent LSN) moved the chosen LSN `1/E0000778` → `1/E1000638`; revert restored the original. Pointing the ranker at `injection_log.json` was caught by strace and by `lab-evaluate-arm --validate-coordinate` peek-flag rejection.

`selection_inputs.read_injection_log` / `read_oracle_optimum` / `read_provenance` are all `false` on both arms.

---

## 6. Do not re-litigate

- Article I–XV, ADR-P1.1-1..4, ADR-P2-1..7, ADR-P2.1-1, ADR-P3-1..7
- One slot `lab_slot` in `labdb`. Never `lab-capture stop` to "restart". Use `lab-consumer stop/start <incident>`.
- Stop PostgreSQL before `lab-reset`. After T1/T2, wait `lab-barrier` / `lab-slot --check`.
- Guest `/tmp` is `noexec`.
- All LSN comparison is integer `(high<<32)+low`. The `3/9` vs `3/10` trap is covered by `lab-candidates --lsn-order-fixture`.
- `lab-verify-p2` AC-P2-17 copies a frozen `db.jsonl` onto **current** evidence. Backup the headline ledger first (`logs/review/D010/db.jsonl.pre_nested`).

---

## 7. Next tranches (anti-inversion guard)

P3's anti-goals are **P3's**. They must not be copied forward as if they constrained P4–P6:

| Tranche | What it builds |
| --- | --- |
| **P4** | **Restore + validation** against the chosen `arm-coordinate`. The harness performs the restore; the arm never does. |
| **P5** | **Builds the representations R0, R1 and R2** over the same provenance-blind ledger. |
| **P6** | **Builds the Arm B model harness** — a modest local model querying those representations. |

P5 is measured against the Arm A number in this file. P5 still must not read `principal` for detection (Article II / `capture-completeness.md` §5). P4 must refuse a coordinate whose peek flags are `true`.

---

## 8. Nested-gate caveat (D010)

`AC-P3-18` re-ran all five prior gates against `archive/current` = the frozen headline incident. They are **not** all green. P3 does not rebuild P1 to manufacture that (same class of caveat as P2.1 Y004). Nested `lab-verify-p2` started `lab-consumer` on the headline id and began appending WAL; D010 stopped that unit and restored `db.jsonl` from `logs/review/D010/db.jsonl.pre_nested` (667 records, mode 0444).

| Gate | Result | Why |
| --- | --- | --- |
| `lab-verify` (P0) | **15/18** | headline consumer stopped; slot inactive; retained WAL over threshold |
| `lab-verify-p1` | crash | `lab-analyse-stub` empty stdout on the pinned P1 incident `SC-01_20260820T051544Z` |
| `lab-verify-p1.1` | crash | `PermissionError` writing the frozen `db.jsonl` (mode 0444) |
| `lab-verify-p2` | **16/18** | AC-P2-17 nested prior gates not 18/18 |
| `lab-verify-p2.1` | **14/16** | AC-P2.1-13 nested P2 not 18/18 |

Contract hashes, including `capture-completeness.md` = `59aeaa61281f211046b953a0641de72dc55c3f6cecc7278ee45802d41003d647`, re-verify independently. `bin/lab-verify-p3` is **TIER M 16/18 · TIER A 1/1 · TOTAL 17/19** (AC-P3-18/17 red on nested colour). The P3 analytics, ranker, headline, and contracts are the 16 mechanical P3 criteria that are green.
