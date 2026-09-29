# Plan — P1.1: Provenance & Lab-State Remediation

## Architecture decisions (locked)

### ADR-P1.1-1 — `harness_commit` is HEAD at row-production time, and a dirty tree refuses the row

The row field is defined by the frozen contract as the commit that produced the row. The only faithful implementation
is to read `git rev-parse HEAD` in the deploy root at the instant the row is assembled, inside `bin/lab-evaluate-arm`.
Recording HEAD is necessary but not sufficient: if the working tree has uncommitted changes, HEAD does not describe
the code that ran. Therefore `lab-evaluate-arm` first runs `git status --porcelain --untracked-files=all`; if the
output is non-empty it writes no row and exits non-zero, listing the offending paths.

We choose **refusal over an `harness_dirty` flag**. Adding a flag would require a new results-row field, and the
schema is frozen; more importantly, refusal enforces the discipline that experimental rows are only ever produced
from committed code, which is what makes `harness_commit` a usable reproducibility handle. `HARNESS_COMMIT_AT_P1_OPEN`
is kept as an honest record of the commit at P1 open and is documented as such; it is simply never again the source
of a per-row value. The false note in the handoff that claimed rows *already* record HEAD at evaluate time is
corrected so a future agent does not "restore" the broken behaviour on the strength of it.

### ADR-P1.1-2 — quarantine P1 stub rows by path, never by a schema change

The P1 null run appended real, schema-valid rows whose `harness_commit` is wrong (P1-open commit) and whose
`restore_verdict`/`consistency_verdict` are `stub`. They must never enter the analysis. Because the results-row schema is
frozen, we cannot add a `fixture` field. We instead relocate them under `results/fixtures/` and record provenance in
`results/fixtures/MANIFEST.md`. The convention — established here and inherited by P3+ — is that analysis reads only
`results/*.jsonl` and never descends into `results/fixtures/`. This preserves the frozen schema and makes the
exclusion a property of location, which is trivially auditable.

### ADR-P1.1-3 — readiness is a mechanical gate that never mutates state

`bin/lab-ready` is read-only. It answers one question — "is the lab in a valid state to begin P2 capture?" — by
re-deriving live facts (consumer unit state, `pg_replication_slots`, `lab-slot --check`, presence and growth of the
incident `db.jsonl`) and printing them as one JSON object. It fixes nothing. Repair is a **separate, documented
runbook** a human runs deliberately, because the correct repair for an invalidated slot (roll back to a T1/T2
snapshot that still holds the slot) is destructive to victim state and must not happen as a side effect of a check.
Creating a fresh slot to clear `wal_removed` is explicitly prohibited: it would desynchronise the slot from the
host-side ledger and silently corrupt the evidence stream.

### ADR-P1.1-4 — P2 is blocked on this gate

P2's entry condition becomes `bin/lab-ready` exit 0. This converts "ready for P2", previously a sentence in a memo,
into a precondition the next tranche's W001-equivalent must check. It is recorded here so P2 inherits it.

## Constitutional change

Article XIV is appended by X001. It generalises D1 into a principle:

> **Article XIV — Provenance of record.** Any artefact that records the identity of the code, data or configuration
> that produced an experimental result must name the exact state that produced it, re-derived at production time.
> Where that state is versioned, the recorded identity must be the version control HEAD at production time, and the
> producer must refuse to emit a result when the tracked tree has uncommitted changes. A provenance field that can
> name a state other than the one that produced the artefact is a defect regardless of whether it is currently
> accurate.

This sits alongside Article XII (no test hatches in boundary components) and Article XIII (verification tiers) as the
third lesson learned from review, each closing a class rather than an instance.

## Task breakdown

| Task | Owns | Closes |
| --- | --- | --- |
| X001 | Article XIV; corrects the false handoff note | D1 class |
| X002 | `bin/lab-evaluate-arm` provenance fix + dirty-tree refusal | D1 |
| X003 | `results/fixtures/` quarantine + manifest | D1 fallout |
| X004 | `bin/lab-ready` + recovery runbook | D2 |
| X005 | planned-vs-completed disambiguation | D3 |
| X006 | `bin/lab-verify-p1.1` gate + memo update | all |

## Sequencing

X001 first (principle before repair). X002 depends on X001. X003 depends on X002 (so the quarantine manifest can
state that future rows are correctly provenanced). X004 and X005 are independent of each other and may run in either
order after X003. X006 is the gate and runs last.

## Risks

- **Rolling back to repair the slot destroys the current victim state.** That is acceptable here: P1's incident is a
  stub-only null run and its rows are being quarantined regardless. The runbook states this explicitly so the
  operator is not surprised.
- **A future agent re-reads the corrected handoff note and mis-repairs.** Mitigated by X001 correcting the note and by
  Article XIV making the intended behaviour a constitutional requirement, not a comment.
