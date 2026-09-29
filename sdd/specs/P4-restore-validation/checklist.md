# Checklist — P4: Restore, Validation & the Promotion Gate

The agent fills `Date` and `Bundle` when a task completes. **The operator owns the `Reviewed` column** — the agent
never ticks it.

| Task | Title | Date | Bundle | Reviewed |
| --- | --- | --- | --- | --- |
| E001 | Freeze both P4 contracts; record entry gate | 2026-08-25 | logs/review/E001/ | [ ] |
| E002 | `bin/lab-restore-db` PITR into sandbox cluster | 2026-08-25 | logs/review/E002/ | [ ] |
| E003 | `bin/lab-restore-fs` ZFS clone restore | 2026-08-25 | logs/review/E003/ | [ ] |
| E004 | `bin/lab-restore` cross-layer orchestrator + skew | 2026-08-25 | logs/review/E004/ | [ ] |
| E005 | `bin/lab-validate` row/byte/schema comparison | 2026-08-25 | logs/review/E005/ | [ ] |
| E006 | `bin/lab-verdict` 4-level consistency verdict | 2026-08-25 | logs/review/E006/ | [ ] |
| E007 | `bin/lab-promote` guarded promotion gate | 2026-08-25 | logs/review/E007/ | [ ] |
| E008 | oracle<->reality agreement + victim/evidence safety | 2026-08-25 | logs/review/E008/ | [ ] |
| E009 | loop-closing headline + discrimination negatives | 2026-08-25 | logs/review/E009/ | [ ] |
| E010 | `bin/lab-verify-p4` gate; hashes re-verified; handoff | 2026-08-25 | logs/review/E010/ | [ ] |

## Operator review order

1. `RESULT` line and `VICTIM+EVIDENCE UNTOUCHED` line of the agent's report.
2. `logs/review/<task>/acceptance.md` — **check the tier column**, not just PASS.
3. The negative-test evidence. Confirm the check went red, then green again after revert.
4. `observations.md` — deviations and out-of-scope findings.
5. Hand spot-check two artefacts. For **E009**, feed the TRUE ground-truth coordinate yourself and confirm the verdict
   is `correct` with zero mismatches; then restore a post-damage coordinate and confirm it does NOT validate clean.
   For **E002/E003/E008**, confirm the victim+evidence manifest is byte-identical before and after a restore.

## Acceptance criteria coverage

| AC | Tier | Owning task |
| --- | --- | --- |
| AC-P4-01 | M | E001 |
| AC-P4-02 | M | E002 |
| AC-P4-03 | M | E002 |
| AC-P4-04 | M | E003 |
| AC-P4-05 | M | E004 |
| AC-P4-06 | M | E005 |
| AC-P4-07 | M | E005 |
| AC-P4-08 | M | E005 |
| AC-P4-09 | M | E006 |
| AC-P4-10 | M | E006 |
| AC-P4-11 | M | E007 |
| AC-P4-12 | M | E007 |
| AC-P4-13 | M | E009 |
| AC-P4-14 | M | E009 |
| AC-P4-15 | M | E008 |
| AC-P4-16 | M | E008 |
| AC-P4-17 | M | E010 |
| AC-P4-18 | M | E010 |
| AC-P4-19 | A | E010 |

Eighteen of nineteen criteria are tier M. The single tier A criterion is the handoff record, which asserts on
machine-readable fields, per Article XIII.

## Tranche exit condition

P4 is accepted when `bin/lab-verify-p4` reports every criterion PASS with per-tier totals printed separately and is
itself proven read-only over the evidence root; both P4 contracts are frozen and hash-verified; DB PITR into a sandbox
and FS `zfs clone` are both proven non-destructive to the victim; the cross-layer coordinate resolves by integer LSN
with recorded skew; row/byte/schema validation against the oracle manifest works and discriminates; the 4-level verdict
is deterministic; the promotion gate refuses without a clean verdict and an explicit token and only ever simulates in
the lab; the loop-closing headline yields `correct` with zero mismatches on the true coordinate; Arm A's real-restore
outcome agrees with the P3 oracle score; the victim+evidence-untouched safety property holds; all sandbox resources are
torn down; all prior gates, regression and contract hashes (through P3.1) are unchanged; and the P4 handoff is written
without anti-goal inversion.

## Note for P5 and P6

- **P5** (representations R0/R1/R2) and **P6** (Arm B) reuse this restore+validate harness unchanged: a model-chosen
  `arm-coordinate` is fed to `bin/lab-restore` -> `bin/lab-validate` -> `bin/lab-verdict` exactly as Arm A's is, so
  Arm B is scored identically. Do not fork the restore path for Arm B.
- The **walking-skeleton milestone** (P0-P4 + SC-01) is reached at P4 acceptance. Protect it above all other work.
