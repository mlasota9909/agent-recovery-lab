# P4 Restore, Validation & the Promotion Gate — Architecture Handoff (tranche close)

**Date:** 2026-08-25  
**Status:** P4 **COMPLETE** — walking-skeleton milestone (P0–P4 + SC-01). Restore is sandbox-only; the frozen headline is untouched.  
**Gate:** `bin/lab-verify-p4` **TIER M 18/18 · TIER A 1/1 · TOTAL 19/19**  
**Human review:** `sdd/specs/P4-restore-validation/checklist.md` Reviewed column still ☐.

Load this file **together with** `docs/P3.1-architecture-handoff.md` and `docs/P3-architecture-handoff.md`. P5 builds representations R0/R1/R2. P6 builds the Arm B model harness. Both reuse this restore+validate path unchanged. P4's anti-goals (do not restore into the victim, do not `zfs rollback`, do not emit `authorized` in the lab) are **P4's** — they are not P5/P6 scope.

```json
{
  "article_count": 16,
  "walking_skeleton": true,
  "mechanism": "zfs clone of labpool/victim/pgdata@snap + host WAL PITR into labpool/sandbox; zfs clone of labpool/victim/protected@snap",
  "sandbox_port_base": 55432,
  "ground_truth_verdict": "correct",
  "ground_truth_lsn": "1/E1000000",
  "ground_truth_snapshot": "s_20260824T091643Z",
  "ground_truth_summary": {
    "damage_rows_retained": 0,
    "legit_rows_lost": 0,
    "files_mismatched": 0,
    "schema_diffs": 0
  },
  "too_late_verdict": "incorrect-corrupt",
  "too_late_lsn": "1/E50007A8",
  "too_late_damage_rows_retained": 200,
  "too_early_verdict": "incorrect-safe",
  "too_early_lsn": "1/E0000778",
  "too_early_legit_rows_lost": 8,
  "arm_a_p3_analytical": {"damage_rows_retained": 0, "legit_rows_lost": 48},
  "arm_a_p4_summary": {"damage_rows_retained": 0, "legit_rows_lost": 8},
  "arm_a_p3_formula_rederived": 48,
  "cross_layer_skew_ms_arm_a": 30725,
  "cross_layer_skew_ms_ground_truth": 276,
  "lab_ready_blocked_by": "frozen_headline_d2",
  "headline_incident": "SC-01_20260824T091611Z",
  "headline_db_jsonl_sha256": "bf21fff2c7c71b39a150d15c9d097c797006139497c51b5a865414433a1ac7dd",
  "headline_db_jsonl_bytes": 148569,
  "headline_db_jsonl_mode": "0444",
  "victim_zfs_sha256": "5bd10946daf19b2f9241343f804fba967d7e77dd3216f7aff31e56d0b104d507",
  "victim_plus_evidence_combined_sha256": "95d06eb3dcdbc70664bf49cdad1a60cd182ed856571dcd56cb8bc868edf21550",
  "restore_report_sha256": "974815821369d1e1477e65851cf0ba39e23e156adf63c5e3840baafa5b30d357",
  "promotion_gate_sha256": "edaaeaca69a5b9dbec1172c811b26387b9887f46d8125ab84a29c18442eddfe7",
  "capture_completeness_sha256": "59aeaa61281f211046b953a0641de72dc55c3f6cecc7278ee45802d41003d647",
  "harness_commit_at_reports": "e84d5be88c1582e565622a2fdadec0e44926583d",
  "naive_named_snapshot_absent": "s_20260824T091654Z",
  "anti_goal_inversion": false,
  "p5": "builds representations R0/R1/R2",
  "p6": "builds Arm B model harness",
  "p4": "restore+validation against the chosen coordinate (this file)"
}
```

---

## 1. Where the build stands

```
P0    substrate ............. DONE
P0.1  remediation ........... DONE
P1    instruments ........... DONE
P1.1  provenance ............ DONE
P2    capture ............... DONE
P2.1  reconciliation ........ DONE
P3    analytics + Arm A ..... DONE (accepted after P3.1)
P3.1  gate integrity ........ DONE
P4    restore + validation .. THIS FILE — walking-skeleton milestone
P5    representations ....... NEXT — builds R0 / R1 / R2
P6    Arm B model harness ... NEXT AFTER P5 — modest local model over those representations
```

P4 built **no representation, no model, no re-fit of Arm A or naive**. Frozen contracts were **not** edited. SC-01 headline hashes are byte-identical to the P3.1 close.

---

## 2. Restore mechanism

The host has **no postgres server**. The incident `basebackup/` directory is empty (mkdir at incident open). Restore materialises as:

1. **DB.** `zfs clone labpool/victim/pgdata@<snap> labpool/sandbox/<incident>/<tag>/pgdata`. Copy archived WAL from the **host** `archive/<incident>/` into the clone's `wal/` (starting 1–2 segments before the snapshot LSN). Write `postgresql.conf` **inside the clone** (`archive_mode=off`, `wal_level=logical` because the clone still contains `lab_slot`, `recovery_target_action=pause`). `pg_ctl -D <clone>` as `postgres` on the guest. `psql -h 127.0.0.1 -p <sandbox_port>`.
2. **FS.** `zfs clone labpool/victim/protected@<snap> labpool/sandbox/<incident>/<tag>/protected`.
3. **Never** `pg_ctl`/`systemctl` the victim cluster. **Never** `zfs rollback` of `labpool/victim*`. Teardown is `zfs destroy` of `labpool/sandbox/...` only.

Sandbox port = `SANDBOX_PORT` (55432) + `crc32(tag) % 200`. Concurrent tags must not collide; `too_late` and `ground_truth` collided under the original modulus 40.

---

## 3. Loop-closing result

Restoring the known ground-truth coordinate `1/E1000000` / `s_20260824T091643Z` yields `consistency_verdict=correct` with all summary counts zero. That is the apparatus test: the perfect coordinate reproduces the pre-incident oracle-manifest state.

Discrimination:

| coordinate | LSN | verdict | what it proves |
| --- | --- | --- | --- |
| ground-truth | 1/E1000000 | `correct` | apparatus can go green |
| too-late (naive) | 1/E50007A8 | `incorrect-corrupt` (damage=200) | validator is not a rubber stamp |
| too-early (Arm A) | 1/E0000778 | `incorrect-safe` (legit_lost=8) | too-early is reported as legitimate loss, not as clean |

Naive's named snapshot `s_20260824T091654Z` is **gone** after a historic T1 rollback. The integer resolver picks `s_20260824T091643Z`. WAL still replays to `1/E50007A8`.

---

## 4. P3 analytical vs P4 summary

P3 scored Arm A as damage 0 / legit_lost **48** without restoring. That 48 counts every workload-manifest row **after** the chosen LSN, including 40 post-optimum capture-window ops (32 of them after the inject).

P4 `summary.legit_rows_lost` counts only ops the **optimum contained** and this restore missed (`chosen < LSN <= optimum`). Arm A is **8**. The P3 number is re-derived as `p3_analytical_legit_rows_lost=48`. Damage agrees 0=0.

Using P3's 48 as the verdict summary would make the ground-truth coordinate `incorrect-safe` (40) even when the restored state matches the oracle manifest. Contract §5 defines `correct` as matching the manifest. The vs-optimum count belongs in `summary`.

---

## 5. Safety

Whole-of-victim-plus-evidence manifest (ZFS guid/snapshot list + evidence-root SHA-256) was `95d06eb3…` before restore, after restore, and after teardown. Victim postgres on 5432 stayed up. Headline `db.jsonl` remained `bf21fff2…` / 0444 / 148569 bytes.

`bin/lab-ready` still exits 1 on this frozen headline (`consumer_unit_state,slot_active,slot_check,db_jsonl_growing`). Starting the consumer would mutate victim WAL and the 0444 ledger — forbidden. Recorded as `lab_ready_blocked_by=frozen_headline_d2`, not as a fake exit 0.

Promotion is simulation only. `decision=authorized` is unreachable in this lab.

---

## 6. Do not re-litigate

- Article I–XVI, ADR-P1.1-1..4, ADR-P2-1..7, ADR-P2.1-1, ADR-P3-1..7, ADR-P3.1-1..4, ADR-P4-1 (restore read-only vs victim+evidence)
- One slot `lab_slot` in `labdb`. Never `lab-capture stop`. Headline consumer **stopped**.
- **Never** `zfs rollback` of `labpool/victim*`. **Never** `pg_ctl` the victim as part of restore.
- All LSN comparison is integer `(high<<32)+low`.
- **Do not** mutate frozen contracts. **Do not** re-fit Arm A or naive. **Do not** change SC-01 headline numbers.
- `bin/lab-verdict` refuses a dirty tree (Article XIV). `var/` is gitignored so restore artefacts do not dirty the harness.
- Do **not** run live `bin/lab-verify` (P0) against the frozen headline (D2). Use `bin/lab-regression`.
- Guest `/tmp` is `noexec`. Sandbox `psql` uses `-h 127.0.0.1`.

---

## 7. Next tranches (anti-inversion guard)

P4's anti-goals are **P4's**. They must not be copied forward as if they were P5's or P6's scope:

| Tranche | What it builds |
| --- | --- |
| **P5** | **Builds the representations R0, R1 and R2** over the same provenance-blind ledger. |
| **P6** | **Builds the Arm B model harness** — a modest local model querying those representations. |

P5/P6 feed an `arm-coordinate` to `bin/lab-restore` → `bin/lab-validate` → `bin/lab-verdict` exactly as Arm A is scored. Do not fork the restore path for Arm B.

---

## 8. Backup

`BACKUP_PREFIX=thesis-p4 bin/lab-repomix-backup` → `backups/thesis-p4-<UTC>.md` and `backups/repomix-latest.md`. Pack includes SDD, `bin/`, `lib/`, P4 specs, E* review markdown/json/txt, this handoff. WAL archive, evidence jsonl, results jsonl, and keys remain excluded.
