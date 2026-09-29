# P0 acceptance tiers (R004)

Generated for P0.1. Article XIII: every criterion is mechanical (M) or attested (A).
Attested criteria still assert on a machine-readable field, never a token in prose.

P0 originally verified seven criteria against live state and eleven via `review_pass()`
on agent markdown. R004 deletes that helper, upgrades AC-6 and AC-14 to live mechanical
checks, and re-points the remaining nine attested criteria at committed JSON or `lab.env`.

| ID | Tier | Justification |
| --- | --- | --- |
| AC-1 | M | Live literal sweep of `bin/` against `lab.env` values |
| AC-2 | A | One-time device-attachment proof; asserts `DEV_LOCATION=guest` in `lab.env` and `etc/acceptance-attested.json` |
| AC-3 | A | One-time T002 timings; asserts `snapshot_seconds<2` and `rollback_seconds<5` in attested JSON |
| AC-4 | A | One-time snapshot-read; asserts attested `deleted_content` is present in `logs/review/T013/snapshot-read-proof.txt` |
| AC-5 | A | One-time zfs-diff parse; asserts `+ - M R` in `logs/review/T013/zfs-diff-parsed.json` |
| AC-6 | M | Live UPDATE then DELETE; decoded `identity.payload` must equal the pre-change column value |
| AC-7 | A | T014 DDL ordering artefact; markers present and `record_lsn` strictly ordered by integer LSN |
| AC-8 | A | T007 overwrite artefact; `refusal_exit=42` and checksum appears twice (before/after) |
| AC-9 | A | T005 incident disjointness recorded in attested JSON |
| AC-10 | M | Live `lab-slot --check` (fail-closed: active, under threshold, not invalidated) |
| AC-11 | A | T008 provenance; attested principals equal `ROLE_APP`/`ROLE_AGENT` |
| AC-12 | M | Live isolation suite plus `--enumerate` (≥12 candidates) |
| AC-13 | M | Live `--regression` three-phase PASS/FAIL/PASS by host-side mutation |
| AC-14 | M | Live last-20 heartbeat rows: ~1 Hz, newest row fresh, LSNs strictly monotonic by `(high<<32)+low` |
| AC-15 | M | Live `lab-snapshots` valid anchors |
| AC-16 | M | Live `lab-coordinate` on newest valid snapshot |
| AC-17 | A | T012 three-tier reset; attested `t1_elapsed_ms>0` |
| AC-18 | M | Live idempotence sweep of T001–T010 CLIs |

Split: **9 mechanical, 9 attested**. The WI's "roughly 11/7" assumed nine pre-existing mechanical
criteria; the P0 verifier had seven live checks. Upgrading AC-6 and AC-14 yields 9/9.

`bin/lab-verify` prints `TIER M: 9/9 PASS · TIER A: 9/9 PASS · TOTAL: 18/18`. There is no
undifferentiated "18/18" headline. `--json` emits `{criteria, totals}`.
