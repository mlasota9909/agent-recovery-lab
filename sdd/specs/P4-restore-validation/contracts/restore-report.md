# FROZEN CONTRACT — Restore Report (the validation verdict record)

**Contract ID:** restore-report
**Frozen by:** E001
**Status:** FROZEN — changes only by amendment-through-supersession (Article XV).
**Produced by:** `bin/lab-validate` + `bin/lab-verdict` (E005, E006), assembled by the restore orchestrator (E004).
**Consumed by:** the operator, the P4 headline test (E009), and the oracle<->reality agreement check (E008).

## 1. Purpose

Every restore-and-validate cycle emits exactly one **restore report**: a machine-readable record of what was restored,
how the restored state compared to the ground-truth oracle manifest at row/byte/schema level, the resulting
consistency verdict, the promotion decision, and the proof that the victim and evidence store were left untouched.
This is the artefact the whole tranche is judged on, and the record real-restore outcomes are reported from.

## 2. Hard rules

- **R1 — one report per restore.** A report describes a single coordinate restored for a single incident. The
  `restore_of` field names what the coordinate came from: an arm (`arm_a`, `naive`, `arm_b`) or `ground_truth`
  (the known optimum, used by the loop-closing test).
- **R2 — validation reads the oracle manifest only to compare, never to choose.** The coordinate is an input. The
  oracle manifest is read to score the restored state (Article II scoring role), never to select or adjust the
  coordinate.
- **R3 — integer LSN.** `coordinate.lsn_int` is authoritative; `lsn_text` is the human/Postgres form. No string LSN
  comparison anywhere in restore or validation.
- **R4 — the verdict is one of four fixed values** (see §5). It is a deterministic function of the validation
  results; the same restored state -> the same verdict.
- **R5 — validate != promote.** A report produced by validation always has `promotion.decision` in
  {`withheld`, `simulated`}. `authorized` may appear only when an explicit operator token was supplied to
  `bin/lab-promote` (see `promotion-gate.md`). Validation never sets `authorized`.
- **R6 — the safety block is mandatory and mechanical.** `safety.victim_untouched` and `safety.evidence_untouched`
  are computed by comparing a whole-of-victim-plus-evidence manifest hash before and after the cycle
  (`manifest_before` == `manifest_after`). A report with either `false` is a failed restore, regardless of the verdict.
- **R7 — provenance-blind selector.** `selector_provenance.arm_no_peek_ok` must be `true`: P4 refuses to restore
  against an arm coordinate whose `selection_inputs` no-peek check failed (arm-coordinate §4).

## 3. Record schema (one JSON object per restore)

| Field | Type | Meaning |
| --- | --- | --- |
| `incident_id` | string | the incident restored |
| `restore_of` | string | `arm_a` / `naive` / `arm_b` / `ground_truth` — the source of the coordinate |
| `coordinate` | object | `lsn_text`, `lsn_int`, `snapshot`, `skew_ms` (cross-layer skew at this coordinate) |
| `db_validation` | object | `relations_checked`, `relations_matched`, `mismatches[]` (per-relation) |
| `fs_validation` | object | `files_checked`, `files_matched`, `mismatches[]` (per-file) |
| `schema_validation` | object | `ddl_match` (bool), `diffs[]` |
| `summary` | object | `damage_rows_retained`, `legit_rows_lost`, `files_mismatched`, `schema_diffs` (all integers) |
| `consistency_verdict` | string | one of the four values in §5 |
| `promotion` | object | `decision` (`withheld`/`authorized`/`simulated`), `clean_verdict` (bool), `authorized_by` (string\|null), `simulated` (bool) |
| `restore_target` | object | `sandbox_pgdata`, `sandbox_port`, `fs_clone_dataset` — where the restore was materialised |
| `safety` | object | `victim_untouched` (bool), `evidence_untouched` (bool), `manifest_before` (hash), `manifest_after` (hash) |
| `selector_provenance` | object | `restored_against_arm`, `arm_no_peek_ok` (bool) |
| `harness_commit` | string | git HEAD of the harness that produced this report (Article XIV), computed at report time on a clean tree |

## 4. Mismatch record (an element of `db_validation.mismatches[]` / `fs_validation.mismatches[]`)

| Field | Type | Meaning |
| --- | --- | --- |
| `object` | string | relation name (DB) or file path (FS) |
| `kind` | string | `row_count` / `content_hash` (DB); `byte_hash` / `missing` / `extra` (FS) |
| `expected` | string | the oracle-manifest value |
| `actual` | string | the restored-state value |
| `classification` | string | `damage_retained` (restored has damage the optimum did not) or `legit_lost` (restored missing legitimate state the optimum had) |

## 5. The consistency verdict (four fixed values)

| Verdict | Meaning |
| --- | --- |
| `correct` | restored state matches the oracle manifest exactly at row, byte and schema level: zero damage retained, zero legitimate loss |
| `incorrect-safe` | restored state is internally consistent but not the optimum: no damage retained, but some legitimate work lost (coordinate too early) |
| `incorrect-corrupt` | restored state retains damage the optimum eliminated (coordinate too late), and/or is internally inconsistent |
| `not-recovered` | the restore did not produce a usable, consistent instance at all (replay failed, clone failed, cluster would not start) |

## 6. Example (illustrative, non-normative)

```json
{
  "incident_id": "SC-01-20260825T0100Z-a1",
  "restore_of": "arm_a",
  "coordinate": {
    "lsn_text": "3/C4B2FE",
    "lsn_int": 12897342,
    "snapshot": "labpool/victim@snap_0007",
    "skew_ms": 420
  },
  "db_validation": {
    "relations_checked": 6,
    "relations_matched": 6,
    "mismatches": []
  },
  "fs_validation": {
    "files_checked": 118,
    "files_matched": 118,
    "mismatches": []
  },
  "schema_validation": {
    "ddl_match": true,
    "diffs": []
  },
  "summary": {
    "damage_rows_retained": 0,
    "legit_rows_lost": 0,
    "files_mismatched": 0,
    "schema_diffs": 0
  },
  "consistency_verdict": "correct",
  "promotion": {
    "decision": "withheld",
    "clean_verdict": true,
    "authorized_by": null,
    "simulated": false
  },
  "restore_target": {
    "sandbox_pgdata": "/home/mlasota/thesis/var/sandbox/SC-01-20260825T0100Z-a1/pgdata",
    "sandbox_port": 55432,
    "fs_clone_dataset": "labpool/victim/protected@\u2026->labpool/sandbox/SC-01-\u2026"
  },
  "safety": {
    "victim_untouched": true,
    "evidence_untouched": true,
    "manifest_before": "sha256:9f\u2026",
    "manifest_after": "sha256:9f\u2026"
  },
  "selector_provenance": {
    "restored_against_arm": "arm_a",
    "arm_no_peek_ok": true
  },
  "harness_commit": "c0ffee1"
}
```

## 7. Change control

Frozen at E001 and hash-recorded in `logs/review/E001/`. Later changes supersede via `restore-report.amendment-N.md`
with its own ADR; this file stays byte-identical (Article XV).
