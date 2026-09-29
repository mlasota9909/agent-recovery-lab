# Plan — P4: Restore, Validation & the Promotion Gate

## Architecture decisions (locked)

These continue the ADR lineage (ADR-003 deterministic scoring; ADR-008 the cross-layer coordinate; ADR-P2-7 entry
behind reconciliation; ADR-P3-5 integer LSN) and add the decisions specific to real restore and validation.

### ADR-P4-1 — restore is read-only with respect to the victim and the evidence store

The single most important decision. A restore reconstructs state into **new sandbox resources** and never mutates the
victim or evidence:

- **DB:** replay the host-side base backup + archived WAL into a fresh cluster with its own PGDATA under
  `var/sandbox/<incident>/pgdata` and its own port. Never `pg_ctl`/`systemctl` the victim cluster; never point
  recovery at the victim's live PGDATA.
- **FS:** `zfs clone` the resolved snapshot into `labpool/sandbox/<incident>`. Never `zfs rollback` the victim dataset
  (rollback is destructive; clone is not).

Enforced mechanically, not by inspection: a whole-of-victim-plus-evidence manifest hash is captured before and after a
full cycle and must be byte-identical (AC-P4-16). This is the P4 analogue of Article XVI's read-only-gate property,
applied to the restore path. It is also why the safety block is mandatory in `restore-report.md` (R6).

### ADR-P4-2 — the oracle manifest is for validation scoring, never for coordinate selection

Validation reads the P1 oracle manifest to compare the restored state against ground truth. That is the oracle's
scoring role under Article II and is legitimate. What is prohibited is using the manifest (or the injection log) to
*choose* or *adjust* the coordinate being restored — P4 restores against a coordinate handed to it. The coordinate's
source is recorded in `restore_of`, and for arm coordinates P4 refuses any whose `selection_inputs` no-peek check
failed (ADR-P4-6). Restore does not get to peek at the answer to pick a better coordinate.

### ADR-P4-3 — validate and promote are separate; promotion is gated and, in the lab, simulated

Validation runs entirely in the sandbox and produces a report; it never promotes. Promotion — replacing the live state
with the restored state — is a distinct step behind two independent gates: a `correct` verdict (R2) and an explicit
operator authorization token (R3). In this lab, even a clean, authorized promotion is a **logged simulation** that
takes no destructive action (R4). This models the real-world control (a human decides to cut over) without ever
endangering the victim or evidence, and keeps the walking skeleton non-destructive and re-runnable.

### ADR-P4-4 — the consistency verdict is a deterministic function of validation, on a fixed 4-level scale

The verdict is not a judgement call. It is computed from the validation results: zero mismatches -> `correct`; only
`legit_lost` mismatches -> `incorrect-safe`; any `damage_retained` mismatch or internal inconsistency ->
`incorrect-corrupt`; no usable instance -> `not-recovered`. The four values are frozen in `restore-report.md` §5 and
map directly onto the roadmap's recovery scale. Determinism is asserted by re-run (AC-P4-09), so there is a
single reproducible verdict per coordinate.

### ADR-P4-5 — cross-layer coordinate resolution reuses lab-coordinate; skew is measured, not solved

The hardest integration problem — reconciling filesystem and database evidence into one coordinate — is
handled by resolving a single LSN to the newest snapshot with `lsn_int <= target` via the existing `bin/lab-coordinate`
(ADR-008), restoring the DB to the exact LSN and the FS to that snapshot, and **recording the residual skew**
(`coordinate.skew_ms`) in the report rather than pretending it is zero. Reported skew is a measured quantity and a
legitimate finding. Integer LSN arithmetic only (ADR-P3-5); the `3/9` vs `3/10` trap is covered (AC-P4-05).

### ADR-P4-6 — restore only against a no-peek-clean coordinate

P4 restores against `arm-coordinate` records (Arm A, naive, later Arm B) and against the `ground_truth` coordinate for
the loop-closing test. For any arm coordinate, P4 checks `selection_inputs.read_injection_log`, `read_oracle_optimum`
and `read_provenance` are all `false` before restoring, and records `selector_provenance.arm_no_peek_ok`. A coordinate
that cheated in selection must not be laundered into a clean-looking restore outcome. The ground-truth coordinate is
exempt from the no-peek check by definition (it *is* the answer) and is labelled `ground_truth` so it can never be
mistaken for an arm result.

### ADR-P4-7 — sandbox teardown is part of done and is itself non-destructive

Each sandbox cluster and each `zfs clone` is torn down after the task that created it (unless a WI explicitly retains
it for a dependent task). Teardown stops only the sandbox cluster (never the victim) and destroys only
`labpool/sandbox/*` datasets (never a `victim` dataset). Leaving an orphaned clone risks pool exhaustion across the
P7 run matrix and risks a later incident reading a stale sandbox; leaving a running sandbox cluster risks port
collisions. Teardown is verified by the same before/after victim+evidence manifest.

## No new constitutional article

P0.1, P1.1, P2.1 and P3.1 each added an article because each was a remediation that surfaced a defect class (XII test
hatches, XIII verification tiers, XIV provenance of record, XV amend-by-supersession, XVI read-only gates). P4 is a
forward build and surfaces no new class; it operates under the sixteen articles in force. The P4 safety rule (ADR-P4-1)
is a strong ADR enforced mechanically, not a new article. If P4's own acceptance review finds a defect class the gate
missed — the pattern in several earlier tranches — that is where Article XVII would come from, not before.

## Task breakdown

| Task | Owns | Serves |
| --- | --- | --- |
| E001 | the two P4 contracts + entry-gate record | FR-1 |
| E002 | `bin/lab-restore-db` — PITR into a sandbox cluster | FR-2 |
| E003 | `bin/lab-restore-fs` — ZFS clone restore | FR-3 |
| E004 | `bin/lab-restore` — cross-layer orchestrator + skew | FR-4 |
| E005 | `bin/lab-validate` — row/byte/schema comparison | FR-5 |
| E006 | `bin/lab-verdict` — the 4-level consistency verdict | FR-6 |
| E007 | `bin/lab-promote` — the guarded promotion gate | FR-7 |
| E008 | oracle<->reality agreement + the victim+evidence-untouched safety property | FR-8 |
| E009 | loop-closing headline + discrimination negatives | FR-9 |
| E010 | `bin/lab-verify-p4` gate; contract re-verify; regression; P4 handoff | FR-10 |

## Sequencing

E001 first (contracts before any producer). E002 (DB restore) and E003 (FS restore) may run in either order after
E001. E004 orchestrates both and depends on E002+E003. E005 validates the E004 output. E006 verdict depends on E005.
E007 promote depends on E006 (it gates on the verdict). E008 (agreement + safety) depends on E006/E007 being wired.
E009 (headline + discrimination) depends on E008. E010 gates and runs last.

```
E001 --+-- E002 --+
       +-- E003 --+-- E004 -- E005 -- E006 -- E007 -- E008 -- E009 -- E010
```

E002 and E003 may run in either order once E001 is complete. E004 needs both. E010 runs last.

## Risks

- **Restore silently touching the victim or evidence.** The highest-consequence risk in the whole project: if restore
  mutates the victim, every subsequent incident is contaminated. Mitigation: ADR-P4-1 and the before/after
  victim+evidence manifest (AC-P4-16), plus a command-log scan for `zfs rollback` / `pg_ctl` against victim resources.
  The negative test deliberately points a restore at the victim dataset and proves the safety check goes red.
- **Coding-agent-generated restore logic that is plausible but wrong** — the failure class this project studies.
  Mitigation: the loop-closing test (feed the true coordinate, must be `correct`) is an independent oracle the restore
  cannot game; and the discrimination negatives prove validation is not a rubber stamp.
- **Validation that always passes (a rubber stamp).** Mitigation: AC-P4-14 discrimination + the E005 negative test
  that injects a manifest mismatch and proves it is caught and correctly classified `damage_retained` vs `legit_lost`.
- **Replay overshooting the target LSN.** Mitigation: AC-P4-03 asserts replay stops at exactly the target and the
  first commit beyond target is absent.
- **String LSN comparison resurfacing in snapshot resolution.** Mitigation: ADR-P3-5 restated; the `3/9` vs `3/10`
  case is required in AC-P4-05.
- **Promotion accidentally destructive, or auto-promoting on a clean verdict.** Mitigation: ADR-P4-3 + `promotion-gate.md`
  R2/R3/R4; the E007 negative test proves promotion refuses without a token and never executes destructively.
- **Orphaned sandbox clusters/clones exhausting the pool or contaminating later incidents.** Mitigation: ADR-P4-7
  teardown is part of done and verified by the same manifest.
- **Read-only gate cost as ledgers grow.** The victim+evidence manifest hashes a lot. If gate time balloons on SC-02+
  ledgers, scope the manifest to the incident under test rather than the whole tree — a known lever, not needed now.

## Carry-forward from the P3.1 review

- **Fixture drift.** The per-tranche regression fixtures are pinned artefacts. If P4 legitimately needs to re-pin a
  fixture (it should not — P4 adds no ledger schema change), the reason must be stated in the handoff (E010).
- **Do not restore against a no-peek-failed coordinate** (P3 review note) — enforced by ADR-P4-6 at the entry gate
  (E001) and per restore.
