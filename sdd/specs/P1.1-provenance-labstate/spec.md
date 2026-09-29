# Spec — P1.1: Provenance & Lab-State Remediation

**Feature ID:** P1.1-provenance-labstate
**Status:** ready for implementation
**Owner:** Maciej Lasota
**Depends on:** P1 (accepted, pending this remediation)
**Blocks:** P2 (capture collectors) — P2 must not start until X004's readiness gate passes

## 1. Purpose

Close the three defects found in the P1 acceptance review, and add the mechanism and the constitutional principle
that stop each defect class from recurring. This tranche changes no frozen contract and builds no intelligence.

## 2. Problem statement

**D1 — `harness_commit` names the wrong commit.** `bin/lab-evaluate-arm` sets each results row's `harness_commit`
to `env("HARNESS_COMMIT_AT_P1_OPEN")`, the commit recorded when the tranche opened at W001. The frozen results-row
contract defines `harness_commit` as *"the git commit of the harness that produced this row."* The two disagree.
There is also no guard against an uncommitted working tree, so even recording HEAD would not be sufficient on its
own: a row produced from edited-but-uncommitted code would name a commit whose contents are not what ran. For a
reproducibility field, this silently records a falsehood. This is the same failure class the whole project exists to
study — a plausible value that is wrong — and it must be closed before any results row is used in analysis.

**D2 — the lab is not in a valid capture state.** The P1 end-state shows the replication slot with
`invalidation_reason=wal_removed` and `slot_active=false`, with the consumer unit disabled. P2's collectors attach to
that logical-decoding stream. Beginning P2 from an invalidated slot yields an incomplete or broken evidence ledger,
and nothing currently gates "ready for P2" — it was asserted in a memo, not verified.

**D3 — planned figures presented as completed work.** The acceptance memo's headline JSON carries
`total_incidents: 10` and `total_arm_runs: 150` alongside `restore_stubbed: true`. No experimental arm has run; these
are planning outputs of the throughput measurement. Presented as top-line totals they misstate the project's state,
which is precisely the kind of overclaim to avoid.

## 3. Scope

### In scope

- **Article XIV** added to the constitution: results-row provenance of record.
- Correcting `bin/lab-evaluate-arm` so `harness_commit` is `git rev-parse HEAD` computed **at row-production time**,
  and refusing to produce a row when the working tree is dirty (`git status --porcelain --untracked-files=all` is
  non-empty). `HARNESS_COMMIT_AT_P1_OPEN` is retained as a record of P1-open provenance but unbound from the row.
- Quarantining every results row produced during P1 (the null-run stub rows) under a `results/fixtures/` path with a
  manifest, so they can never be mistaken for experimental data. The results-row schema is **not** modified.
- `bin/lab-ready`: a mechanical P2-readiness gate over the live slot, consumer, incident pointer and evidence stream,
  plus a documented, tested recovery runbook for the invalidated-slot case.
- Disambiguating planned versus completed counts across `docs/p1-acceptance-memo.md`, `docs/sample-size-plan.md` and
  any throughput artefact, so no document or field states that 150 arm runs have been executed.
- `bin/lab-verify-p1.1`: the tiered gate for this tranche, and an updated acceptance memo recording that P1 was
  accepted only after P1.1.

### Out of scope

- Any change to a frozen contract, or any new field on the results row.
- Any analytics, ranking, representation, retrieval interface, or model invocation.
- Real point-in-time restore or restored-state validation (still P4).
- SC-02/03/04 damage logic.
- Re-running the P1 null run to regenerate stub rows under the corrected `harness_commit` — the fixtures are
  quarantined, not re-blessed. The first correctly-provenanced rows will be the real P3+ runs.

## 4. Functional requirements

- **FR-1 Provenance of record.** `bin/lab-evaluate-arm` computes `harness_commit = git rev-parse HEAD` in the deploy
  root at the moment it assembles the row, and passes it to `bin/lab-results`. If the working tree is dirty it emits
  no row and exits non-zero, naming the dirty paths. `HARNESS_COMMIT_AT_P1_OPEN` is no longer read for this field.
- **FR-2 Fixture quarantine.** All pre-existing P1 results rows are relocated to `results/fixtures/` with a
  `results/fixtures/MANIFEST.md` recording their origin (P1 null run), why they are excluded (stub verdicts and the
  pre-fix `harness_commit`), and the exact prior paths. No live results file outside `results/fixtures/` contains a
  row until real runs exist. Any future aggregation reads only `results/*.jsonl`, never `results/fixtures/`.
- **FR-3 Readiness gate.** `bin/lab-ready` exits 0 only when: the open incident is resolvable from `archive/current`;
  the consumer unit for that incident is `active`; `slot_active=true`; `invalidation_reason` is null; `lab-slot
  --check` exits 0 with retention below the warn threshold; and the incident's `db.jsonl` exists and is being
  appended to. It prints a single JSON object with every checked field. On any failure it exits non-zero and names
  the failed condition. It never mutates state.
- **FR-4 Recovery runbook.** A documented procedure restores readiness from the invalidated-slot state by rolling
  back to a T1/T2 snapshot that still contains the slot, restarting the consumer, running `bin/lab-barrier`, and
  re-checking — explicitly **not** by creating a new slot. The runbook is exercised, not merely written.
- **FR-5 Planned-vs-completed.** Every count that describes intended future work is labelled `planned_*` (or
  otherwise unambiguously qualified) and accompanied by a `completed_arm_runs` figure, which is `0` at P1.1 close.
- **FR-6 Gate and memo.** `bin/lab-verify-p1.1` runs every P1.1 acceptance check with per-tier totals; the acceptance
  memo records the remediation and the "accepted only after P1.1" statement; P0 and P1 contracts are re-hash-verified
  unchanged.

## 5. Acceptance criteria

| ID | Tier | Requirement |
| --- | --- | --- |
| AC-P1.1-01 | M | `constitution.md` contains a well-formed Article XIV stating results-row provenance of record; article count is 14 |
| AC-P1.1-02 | M | The false note claiming rows already record HEAD at evaluate time is corrected in the handoff, with a dated annotation |
| AC-P1.1-03 | M | For a clean tree, a row produced by `lab-evaluate-arm` has `harness_commit` byte-equal to `git rev-parse HEAD` at production time |
| AC-P1.1-04 | M | With a deliberately dirtied tree, `lab-evaluate-arm` produces **no** row and exits non-zero, naming a dirty path |
| AC-P1.1-05 | M | After committing a change, a newly produced row's `harness_commit` equals the **new** HEAD, not the P1-open commit |
| AC-P1.1-06 | M | `harness_commit` is no longer sourced from `HARNESS_COMMIT_AT_P1_OPEN`; the key still exists in `lab.env` and is documented as P1-open provenance only |
| AC-P1.1-07 | M | Every pre-existing P1 results row now lives under `results/fixtures/`; `MANIFEST.md` lists each with its prior path and exclusion reason |
| AC-P1.1-08 | M | No `results/*.jsonl` (outside `results/fixtures/`) contains any row at P1.1 close; the aggregation path excludes `results/fixtures/` |
| AC-P1.1-09 | M | `bin/lab-ready` exits 0 and its JSON shows consumer active, `slot_active=true`, `invalidation_reason=null`, `--check` ok, and `db.jsonl` present and growing |
| AC-P1.1-10 | M | With the consumer stopped (or slot inactive), `bin/lab-ready` exits non-zero and names the failed condition |
| AC-P1.1-11 | M | The recovery runbook restores readiness from an invalidated/inactive slot **without creating a new slot**; `lab-ready` passes afterwards |
| AC-P1.1-12 | M | The memo and plan expose `planned_*` counts and a `completed_arm_runs` field equal to 0; the two are distinct keys |
| AC-P1.1-13 | M | No document or JSON field states or implies that 150 arm runs (or 10 incidents) have been executed; a defined phrase/field sweep is clean |
| AC-P1.1-14 | M | `bin/lab-verify-p1.1` reports every criterion PASS with per-tier totals printed separately, exit 0 |
| AC-P1.1-15 | M | `bin/lab-verify` still 18/18; P0 (R007) and P1 (W002/W010) contract hashes unchanged |
| AC-P1.1-16 | A | `docs/p1-acceptance-memo.md` records the three remediated defects and the statement that P1 was accepted only after P1.1 (asserted on machine-readable fields) |

All criteria are tier M except AC-P1.1-16, which attests a one-time documentation event and still asserts on JSON
fields, per Article XIII.

## 6. Definition of done

`bin/lab-verify-p1.1` green with per-tier totals; Article XIV in force; `harness_commit` correct and dirty-tree-
guarded; P1 stub rows quarantined; `bin/lab-ready` gating P2 with a tested recovery runbook; planned-vs-completed
disambiguated; prior contracts hash-verified unchanged; acceptance memo updated.
