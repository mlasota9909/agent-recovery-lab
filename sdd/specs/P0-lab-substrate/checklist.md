# P0 Sign-off Checklist

Update the row after reviewing each task's bundle at `logs/review/<task>/`. The agent updates `Date` and `Bundle`;
**you** own the `Reviewed` column. Do not let the agent tick `Reviewed`.

| Task | Title | Agent result | Date | Bundle | Reviewed |
| --- | --- | --- | --- | --- | --- |
| T001 | Discover host/guest, verify devices, write `lab.env` | PASS | 2026-08-17 | logs/review/T001/ | ☐ |
| T002 | Create `labpool` + dataset layout | PASS | 2026-08-17 | logs/review/T002/ | ☐ |
| T003 | Relocate PostgreSQL data directory | PASS | 2026-08-17 | logs/review/T003/ | ☐ |
| T004 | Schema, before-images, DDL audit trigger | PASS | 2026-08-17 | logs/review/T004/ | ☐ |
| T005 | Evidence root, archive sink, incident scoping | PASS | 2026-08-17 | logs/review/T005/ | ☐ |
| T006 | Logical decoding, archiving, `wal2json` slot | PASS | 2026-08-17 | logs/review/T006/ | ☐ |
| T007 | Slot retention bound, lag CLI, overwrite refusal | PASS | 2026-08-17 | logs/review/T007/ | ☐ |
| T008 | `lab_app` / `lab_agent` identities, least privilege | PASS | 2026-08-17 | logs/review/T008/ | ☐ |
| T009 | Isolation suite + deliberate regression | PASS | 2026-08-17 | logs/review/T009/ | ☐ |
| T010 | Heartbeat table and 1 Hz writer | PASS | 2026-08-17 | logs/review/T010/ | ☐ |
| T011 | Snapshot LSN capture + coordinate resolver | PASS | 2026-08-17 | logs/review/T011/ | ☐ |
| T012 | Three-tier reset | PASS | 2026-08-17 | logs/review/T012/ | ☐ |
| T013 | Filesystem evidence proof | PASS | 2026-08-17 | logs/review/T013/ | ☐ |
| T014 | Database evidence proof | PASS | 2026-08-17 | logs/review/T014/ | ☐ |
| T015 | Full acceptance suite, freeze contracts | PASS | 2026-08-17 | logs/review/T015/ | ☐ |

## Tranche-level gates

| Gate | Why it matters | ☐ |
| --- | --- | --- |
| `DEV_LOCATION=guest` confirmed | Whole storage topology depends on it | ☐ |
| Recursive snapshot is atomic across pgdata + protected | Cross-layer coordinate would otherwise be approximate | ☐ |
| Before-images present in decoded DELETE and UPDATE | "Damaged data retained" is otherwise unmeasurable | ☐ |
| DDL visible and correctly ordered in the stream | SC-03 is otherwise unmeasurable | ☐ |
| Isolation suite goes red on a real violation | The isolation claim is otherwise unevidenced | ☐ |
| Coordinate resolver never selects a snapshot above target LSN | Most dangerous possible bug in the system | ☐ |
| Skew reported in ms and bytes on every resolution | Converts the "unsolved hardest problem" into a result | ☐ |
| T1 reset leaves evidence byte-identical | Ablation validity depends on it | ☐ |
| Full-cycle time measured | Input to the P1 sample-size plan | ☐ |
| Three contracts frozen | P1 builds on them | ☐ |

## Known limitations

1. Isolation is logical and same-host; physical air-gap and WORM immutability are deployment concerns, deliberately
   out of scope. No measured quantity depends on the evidence store's physical location.
2. Filesystem recovery granularity is bounded by snapshot interval — the real-world constraint SC-02 exists to expose,
   reported per run as a granularity penalty.
3. T0 is a ZFS rollback rather than a libvirt snapshot, for speed and code-path reuse.
4. P0 was accepted only after P0.1 remediation (2026-08-17). Five findings (F-1..F-5) were repaired with evidence; see `docs/p0-acceptance-memo.md`.
5. Acceptance criteria are reported in two tiers. Nine are mechanical (re-derived live); nine are attested against machine-readable fields. Load-bearing AC-6 and AC-14 are mechanical.
6. The evidence channel's accepted command surface is enumerated and tested (`bin/lab-isolation-test --enumerate`), not merely asserted.

## P0.1 remediation notes (2026-08-17)

Do not tick Reviewed. Agent result for P0 tasks remains PASS; these notes record what P0.1 changed after first close.

| P0 task | P0.1 note |
| --- | --- |
| T003 | Stale `${PG_DATA}.pre-zfs` removed (R006); versions pinned in `lab.env` / `docs/environment.md` |
| T007 / T006 | Supervised host consumer; `lab-slot --check` fails closed (R003). Steady-state retained WAL 3360 bytes |
| T009 | Receiver hatch deleted (R002); regression is host-side authorised-key mutation; command surface enumerated |
| T012 | Live-cluster reset guard proven with the running postmaster; no `noexec` workaround (R005) |
| T015 | Prose matcher deleted; per-tier totals; AC-6 and AC-14 live (R004). Full-cycle time remains 49.335 s |
