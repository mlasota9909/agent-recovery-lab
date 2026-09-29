# P7 architecture handoff — addendum (challenges and deviations)

This addendum is for P8 and for operator review. It records what went wrong in execution, what was changed in the harness to finish the tranche, and what was **not** changed. It does not replace `docs/P7-architecture-handoff.md`; that file remains the gate artefact (plan, citations, completeness, findings, P8 statement).

Frozen P7 contracts (`scenario-definition.md`, `run-matrix-plan.md`) were not edited. No Article XV amendment was opened. Eighteen articles remain; P7 adds none. P8 builds the analysis notebook and figures from the complete results file.

---

## 1. How to read the matrix

`results/matrix.jsonl` has **51 rows** (`total_rows == total_planned_runs`). Partition: **25 determinations, 25 refusals, 1 run_failure**.

That partition is experimental **except** where this addendum says a harness bug was repaired first. The one remaining `run_failure` is SC-02 Arm A (no 3σ window). Do not treat the discarded T2 snapshot-missing rows as arm or model failure; they are not in the file.

Canonical live incidents (do not regenerate SC-01):

| Scenario | Archive incident | Results join key | Notes |
| --- | --- | --- | --- |
| SC-01 | `SC-01_20260824T091611Z` | `i_20260824T091611Z_122142` | Banked; referenced; never re-run |
| SC-02 | `SC-02_20260826T095506Z` | `i_20260826T095506Z_62a9e9` | ZFS `post_capture` still on the pool |
| SC-03 | `SC-03_20260826T101320Z` | `i_20260826T101320Z_49c7fd` | Archive snapshots recorded; live ZFS snaps gone |
| SC-04 | `SC-04_20260826T101526Z` | `i_20260826T101526Z_55c087` | Same as SC-03 |

Headline ground truth remains LSN `1/E1000000`. Headline `db.jsonl` and `results/SC-01.jsonl` hashes are unchanged (K005/AC-P7-07). The headline `post_capture` snapshot was already invalidated; do not T2-reset the headline.

---

## 2. What was not changed

| Surface | Status |
| --- | --- |
| P7 frozen contracts | Byte-identical (`scenario-definition.md` `74a9c25f…`, `run-matrix-plan.md` `4665066d…`) |
| P4 restore+validate path and `restore-report.md` | Unchanged (`97481582…`) |
| Representations R0/R1/R2 builders, guard, model pin | Unchanged |
| Arm A 3σ threshold / `lab-rank` | Unchanged. SC-02 Arm A failure is reported, not patched |
| `bin/lab-reset` T012 semantics | Unchanged. SC-01 still uses live T2 |
| Results-row schema / `reset_tier` enum | Unchanged (`t0\|t1\|t2` only) |
| Constitution | Still 18 articles |

---

## 3. Challenges (in the order they blocked the matrix)

### 3.1 Shared-pool T2 destroyed sibling snapshots (root cause of hollow SC-03/SC-04)

T012 `zfs rollback -r` on `DS_PARENT=labpool/victim` is designed for **one** incident. P7 evaluates three live incidents on that same dataset. The first live T2 (SC-02 `post_capture` `s_20260826T095606Z`) destroyed later snapshots (`s_20260826T101*` for SC-03/SC-04). Archive `snapshots.json` still listed them; live ZFS did not.

Live `lab-coordinate --lsn/--time` then queried the guest heartbeat table of whichever incident had been rolled back last. SC-03/SC-04 LSNs (`5/F6+`, `6/…`) are not in the SC-02 postgres. Using live coordinate for those cells would have been wrong even if T2 had not crashed.

**Could not undelete the ZFS snapshots.** Regenerating SC-03/SC-04 would have created new snaps and the next live T2 of a sibling would have destroyed them again.

**Deviation (operational, not a frozen-contract change):** P7 matrix cells do **not** call `lab-reset t2` on the live victim. Coordinates resolve from the frozen archive `snapshots.json` (newest recorded snapshot with `recorded_lsn` ≤ target; naive = last snapshot at or before `approx_incident_time + 20s`). Env `LAB_P7_HOST_COORD=1` (and `LAB_P7_HOST_INCIDENT`) routes `lab-candidates` and `lab-arm-b-extract` through `lib/lab_snapshot_coord.py`. Rows still record `reset_tier: t2` (schema enum) plus `validation_detail.matrix.victim_rollback=false` and `t2_skipped_reason`. Skew is reported as `0` (`resolved_by: snapshot_first`); heartbeat skew cannot be measured without live postgres for that incident.

Commit: `64e11dd`.

### 3.2 First K007 run was complete and scientifically hollow

The first unattended matrix wrote 51 rows and K007 completeness passed. All 17 SC-03 cells and all 17 SC-04 cells were `run_failure` with `lab-reset t2: … target snapshot does not exist`. Completeness is not validity. Those 34 rows were stripped from `results/matrix.jsonl`, `results/SC-03.jsonl` and `results/SC-04.jsonl` so `total_rows` stayed 51 rather than 85. The results-row contract is append-only with `supersedes`; this was an operator rewrite of gitignored experimental output after a harness crash, not a schema mutation. SC-02 rows were kept, including the honest Arm A failure.

### 3.3 P4 `lab-validate` requires SC-01 `oracle-manifest.json`

New scenarios do not write that file. An Arm B determination then died in `p4_score` (`SystemExit`) and, before ADR-P7-5 was wired through, could kill the whole plan. Failed **cells** must become rows.

**Deviation:** `p4_maybe` skips P4 when the manifest is absent (`restore_verdict=stub`, reason in `validation_detail`). The P4 code path is not forked; it is not invented a fake SC-01 manifest. SC-03/SC-04 are not single-coordinate scenarios (AC-P7-14/15).

Commit: `8321ea8`.

### 3.4 Article XIV vs a long unattended matrix

A dirty harness tree must refuse a results-row append. Early matrix starts died after expensive T2 because `harness_commit()` ran too late. `SystemExit` from a rejected row also aborted the plan instead of recording `run_failure`.

**Fixes (P7 harness, not contracts):** `harness_commit()` at the start of `run_cell`; catch `SystemExit` on row reject → `run_failure`; gitignore `evidence/**/*.jsonl.frozen` so sealed ledgers are not “dirty tree.”

Commits: `2b149ae`, `51e16c1`, `51b3f0a`.

### 3.5 Refusal rows vs frozen results-row rule 5

When `chosen_coordinate` is null, all coordinate-error fields including `naive_coord_error_*` must be null. Filling naive error on a refusal made the writer reject the row.

Commit: `77832cf`.

### 3.6 Ledger windowing and leftover consumer

A leftover decode consumer plus T2 rewind appended onto a frozen `db.jsonl`. Deduping by rec_key was the wrong repair (it would drop legitimate distinct events). The correct generate path: **stop the consumer, then `window_ledger`**, seal `db.jsonl` mode 0444, restore the frozen ledger after catch-up. P1 commit-LSN idempotency uses `lab-ledger-verify`, not “every wal2json line.”

Commit: `8730cbb`. SC-03/SC-04 were regenerated once after that corruption (`baf69ec`, then sealed `a753575`); the incidents in the table above are the sealed pair.

### 3.7 F006 admit / analytics still carried SC-01 constants

PB-1 window index 15 and “die if no 3σ” were SC-01 hardcodes. SC-02’s max z was ≈2.13 (no 3σ hit — that is the Arm A `run_failure`). SC-04 3σ fired on negative `window_id`s (origin/heartbeat). P7-local: `probe_params_for` / `pb1_window_index`; PB-4 falls back to the max-score window. **Arm A’s 3σ threshold was not lowered** to manufacture a hit.

### 3.8 Gate pins and `_def_ok` (K010, not experimental)

`lab-verify-p7` compared `kind` / `cites` / `overlaps` as top-level definition keys; they live under `ground_truth` / `corpus_citation` / `confounder`. AC-P7-02 still passed because of `and`/`or` precedence on the gap check. AC-P7-03/04 failed until the special keys were skipped in the generic loop (`lib/lab_verify_p7.py`).

`H001_P6_RUNTIME_AMENDMENT` in `lib/lab_p61.py` still named hash `f323d8df…` after commit `4779f43` left the amendment file at `ee097868…`. The **file** was not edited; the pin was updated to the committed amendment. P6/P6.1 protocol and model-runtime hashes were already matching.

---

## 4. Honest experimental leftovers (do not “fix” in P8)

| Observation | Treat as |
| --- | --- |
| SC-02 Arm A `run_failure`, no 3σ window | Experimental. Ranker requires a 3σ hit; this incident did not have one |
| R0 (all three new scenarios) and R1 (SC-02, SC-03) 5/5 refusals | Experimental. J001: mostly `grammar-noncompliance` (hex+ts, integer `lsn=`, or `window=`+`lsn=` that disagree); one SC-04 R0 `explicit-refusal` |
| SC-04 R1 5/5 determinations, R2 5/5; observed order R1, R2, R0 | Reported. `matches_prediction=false` for SC-04 in `logs/review/K009/headline.json` |
| SC-03 R2 / Arm A chose `5/FB000168` (before optimum `5/FF000000`); naive chose post_capture `6/401F1D0` (after) | Trade-off is the finding (sacrifice=9). Do not collapse to a single pass/fail |
| P4 not scored on SC-02/03/04 determinations | Operational skip (no `oracle-manifest.json`). Do not invent SC-01 probe IDs |
| Host-side `skew_ms=0` | Consequence of archive snapshot_first resolve. Not a claim that FS/DB skew is zero (SC-02 skew is 2718 ms in K002) |

---

## 5. What P8 should consume

- Results: `results/matrix.jsonl` (and per-scenario `results/SC-0{2,3,4}.jsonl`). Filter on `validation_detail.matrix.outcome`. SC-01 remains `results/SC-01.jsonl` (banked).
- Completeness: `logs/review/K007/matrix-completeness.json`.
- Findings: `logs/review/K008/sc03-finding.json`, `sc04-finding.json`, `refusal-diagnosis.json`.
- Headline: `logs/review/K009/headline.json` and `headline.md`.
- Gate: `bin/lab-verify-p7` (21/21 at K010 close).
- Host-side flags on P7 rows: `validation_detail.matrix.host_coord`, `victim_rollback`, `t2_skipped_reason`, `p4_skipped`.

Do not re-run live T2 across SC-02/03/04 on the shared victim without a per-incident sandbox (future work, not a P8 prerequisite). Do not regenerate the SC-01 headline.

---

## 6. Pointers

| Item | Where |
| --- | --- |
| Gate handoff | `docs/P7-architecture-handoff.md`, `docs/P7-handoff.json` |
| Host-side coordinate | `lib/lab_snapshot_coord.py`, `LAB_P7_HOST_COORD` |
| Matrix orchestrator | `lib/lab_matrix.py` |
| T2 skip reason on every new row | `validation_detail.matrix.t2_skipped_reason` |
| Backup | `backups/thesis-p7-20260826T232552Z.md` |
