# ADR-P3.1-1 — Gate-integrity defects D1 and D2 (not retro-justified)

**Status:** accepted  
**Date:** 2026-08-24  
**Tranche:** P3.1  
**Related:** ADR-P3.1-2 (pinned-fixture regression), ADR-P3.1-3 (read-only enforcement), Article XVI

This ADR records two defects found at P3 close (D010). It does not pretend either was correct.

## Observed close

`bin/lab-verify-p3` shipped **TIER M 16/18 · TIER A 1/1 · TOTAL 17/19**. The two red criteria are `AC-P3-17` and `AC-P3-18`. The sixteen P3 analytics/ranker/headline criteria were green. Evidence: `logs/review/D010/verify-p3.out`, `logs/review/D010/prior-gates.log`, `docs/P3-architecture-handoff.md` §8.

## D1 — verification gates mutate the evidence they check

**Symptom.** Nested `bin/lab-verify-p1.1` crashed with `PermissionError: [Errno 13] Permission denied: '.../evidence/SC-01/SC-01_20260824T091611Z/db.jsonl'` (mode 0444). Nested `bin/lab-verify-p2` (AC-P2-17) copies `logs/review/X001/db.jsonl.frozen` onto **current** evidence. Nested `lab-verify-p2` also started `lab-consumer@SC-01_20260824T091611Z`, which appended WAL onto the frozen headline ledger until the unit was stopped and `db.jsonl` restored from `logs/review/D010/db.jsonl.pre_nested`.

**Exact files / criteria.**

| Writer | Criterion | What it wrote |
| --- | --- | --- |
| `lib/lab_verify_p11.py` `restore_frozen_ledger` | AC-P1.1 evaluate-arm prep | `EVIDENCE_ROOT/.../db.jsonl` |
| `lib/lab_verify_p2.py` `restore_frozen_ledger` | AC-P2-17 | current evidence `db.jsonl` |
| `lib/lab_verify_p1.py` `ac23` / `ac_p0_still_green` | AC-P1-23, nested P0 | restore + chmod of incident `db.jsonl`; `lab-consumer start` |
| `lib/lab_verify_p21.py` `ac13` | AC-P2.1-13 | backup/restore of current `db.jsonl` |
| `lib/lab_verify_p3.py` `prior_gates` | AC-P3-18 | chmod + restore of headline `db.jsonl` |

**Resolution.** Article XVI: a gate MUST NOT create, modify, move, chmod or delete anything under the evidence root. Mutable copies live under `logs/review/<id>/scratch/`. Enforced by `bin/lab-gate-readonly-check` (ADR-P3.1-3). The two named write paths are removed in Z002; remaining writers are retargeted the same way so the class is closed.

## D2 — nested regression is structurally impossible to pass green

**Symptom.** `AC-P3-18` (and chained `AC-P2-17`, `AC-P2.1-13`) re-ran live-state prior gates against `archive/current` pointed at the frozen SC-01 headline. A frozen ledger (consumer stopped, `db.jsonl` mode 0444) and a live capture state (consumer active, slot draining, retained WAL below threshold) cannot both hold. The re-run is red for **state** reasons, not because P0–P2.1 code is necessarily wrong.

**Exact files / criteria.** `lib/lab_verify_p3.py` `prior_gates` / `ac18` (AC-P3-18); `lib/lab_verify_p2.py` `ac17` (AC-P2-17); `lib/lab_verify_p21.py` `ac13` (AC-P2.1-13).

**D010 nested-gate table (verbatim from `docs/P3-architecture-handoff.md` §8):**

| Gate | Result | Why |
| --- | --- | --- |
| `lab-verify` (P0) | **15/18** | headline consumer stopped; slot inactive; retained WAL over threshold |
| `lab-verify-p1` | crash | `lab-analyse-stub` empty stdout on the pinned P1 incident `SC-01_20260820T051544Z` |
| `lab-verify-p1.1` | crash | `PermissionError` writing the frozen `db.jsonl` (mode 0444) |
| `lab-verify-p2` | **16/18** | AC-P2-17 nested prior gates not 18/18 |
| `lab-verify-p2.1` | **14/16** | AC-P2.1-13 nested P2 not 18/18 |

**Resolution.** The intent ("prior instruments still work") is preserved. The implementation is replaced: `bin/lab-regression` runs each prior gate against its own pinned healthy fixture in the live-equivalent state that gate expects (ADR-P3.1-2). Against the headline, only read-only assertions remain (contract hashes; gate scripts present and pass `lab-gate-readonly-check`).

## What this ADR does not do

It does not rebuild P1 to fake nested green. It does not mutate frozen contracts. It does not change the SC-01 headline numbers.
