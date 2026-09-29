# P0.1 Sign-off Checklist

Update the row after reviewing each task's bundle at `logs/review/<task>/`. The agent updates `Agent result`, `Date`
and `Bundle`; **you** own the `Reviewed` column. Do not let the agent tick `Reviewed`.

| Task | Title | Agent result | Date | Bundle | Reviewed |
| --- | --- | --- | --- | --- | --- |
| R001 | Constitution Articles XII, XIII; defect inventory | PASS | 2026-08-17 | logs/review/R001/ | ☐ |
| R002 | Remove receiver hatch; external regression; enumeration corpus | PASS | 2026-08-17 | logs/review/R002/ | ☐ |
| R003 | Supervised consumer; incident precondition; slot fails closed | PASS | 2026-08-17 | logs/review/R003/ | ☐ |
| R004 | Verification tiers; delete prose matcher; AC-6/AC-14 mechanical | PASS | 2026-08-17 | logs/review/R004/ | ☐ |
| R005 | Reset guard proven, `noexec`-safe | PASS | 2026-08-17 | logs/review/R005/ | ☐ |
| R006 | Stale directory removed; versions pinned; environment table | PASS | 2026-08-17 | logs/review/R006/ | ☐ |
| R007 | Full suite re-run; P0 checklist updated; acceptance memo | PASS | 2026-08-17 | logs/review/R007/ | ☐ |

## Tranche-level gates

| Gate | Why it matters | ☐ |
| --- | --- | --- |
| `lab-wal-receive` read by hand, start to finish, no conditional read path | This is the file a reviewer would read to test the isolation claim | ☐ |
| Enumeration corpus includes the removed probe string and it is refused | Proves the specific defect cannot silently return | ☐ |
| Regression red phase caused by host-side mutation, not by the component | Otherwise AC-13 still validates the check using a weakness in the thing tested | ☐ |
| Temporary key material, if any, provably destroyed | A stale unrestricted key is a worse defect than the one being fixed | ☐ |
| Consumer survives a kill and resumes without gaps in `db.jsonl` | Evidence continuity across an unattended matrix | ☐ |
| Retained WAL steady-state recorded, and over-threshold now exits non-zero | The 436 MB observation must not be able to pass again | ☐ |
| Opening an incident fails with the consumer down | An incident with no DB evidence must fail at open, not at analysis | ☐ |
| Per-tier totals printed; no single "18/18" headline anywhere | Honest verification reporting | ☐ |
| AC-6 re-derives before-images from a live UPDATE and DELETE | "Damaged data retained" is otherwise unmeasurable | ☐ |
| AC-14 re-derives heartbeat interval and LSN monotonicity live | Coordinate resolution depends on this index | ☐ |
| Reset guard refuses with the cluster live, and no rollback occurred | Protects against corrupting state in a way that mimics a result | ☐ |
| `docs/environment.md` generated from `lab.env`, not hand-written | The environment table must be reproducible | ☐ |

## Hand-verification the operator should do personally

Two of these, chosen at random, are worth more than reading the whole bundle:

- [ ] `grep -n -iE 't009|probe|regression|debug|sentinel' bin/lab-wal-receive` returns nothing
- [ ] `ssh` as the guest `postgres` principal with `SSH_ORIGINAL_COMMAND` set to the old probe string returns non-zero
- [ ] `systemctl status lab-consumer@<incident>` shows active, then `kill -9` the process and confirm it returns
- [ ] `bin/lab-verify --json | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d["criteria"]), {c["tier"] for c in d["criteria"]})'`

## Known limitations and evidence

1. The evidence channel's accepted command surface is enumerated and tested, not merely asserted. Use the
   enumeration corpus and its results as the evidence for the out-of-band isolation claim.
2. Acceptance criteria are reported in two tiers, mechanical and attested, with the load-bearing criteria mechanical.
   State the split honestly in the methodology; it is a strength, not an admission.
3. Slot retention is bounded *and* monitored fail-closed, with steady-state retention measured. Report the measured
   value.
4. Amend the P0 limitations list to record that P0 was accepted only after remediation, and what was remediated. A
   reader who sees a build accepted at first attempt with no defects found will not believe it.
