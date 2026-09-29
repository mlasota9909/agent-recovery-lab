# Plan — P3.1: Gate Integrity (Read-Only Verification & Regression Redesign)

## Architecture decisions (locked)

### ADR-P3.1-1 — both defects are recorded as defects, not retro-justified

The P3 gate closed 17/19 with `AC-P3-17`/`AC-P3-18` red. This ADR records the two root causes exactly as the D010
review found them, with the nested-gate table as evidence:

- **D1 — gates mutate evidence.** `bin/lab-verify-p1.1` writes the frozen `db.jsonl` (0444) and crashed with
  `PermissionError`; `bin/lab-verify-p2` AC-P2-17 copies a frozen `db.jsonl` onto current evidence. A verification gate
  must never change the evidence it inspects.
- **D2 — impossible nested regression.** `AC-P3-18` (and chained `AC-P2-17`, `AC-P2.1-13`) re-run live-state prior
  gates against the frozen headline incident. A frozen ledger (consumer stopped) and a live capture state (consumer
  active, slot draining, WAL below threshold) are mutually exclusive, so the re-run is red for state reasons, not code
  reasons.

The ADR does not pretend either was correct; it names them defects and closes them.

### ADR-P3.1-2 — regression runs against pinned fixtures, not the live headline

The valid intent behind `AC-P3-18` is "prove the prior instruments still work after new code lands." The wrong
implementation was to run them against the one incident that must stay frozen. The fix: capture, once, a small real
incident per prior tranche, reconcile it clean, and hold it **read-only** under `fixtures/regression/<tranche>/` as
that tranche's regression fixture. `bin/lab-regression` places each fixture into the live-equivalent state its gate
expects and runs the gate against it. The headline incident is never used for regression. Fixtures are synthetic lab
data; they are captured through the normal pipeline, not hand-authored, so a gate exercising a fixture exercises real
artefacts.

Why per-tranche fixtures rather than one shared fixture: each gate expects a different lab state (P0 wants a live
draining slot; P2/P2.1 want a reconciled ledger; P3 wants analytics inputs). One fixture cannot satisfy all
simultaneously, which is exactly the confusion that produced D2. Separate fixtures keep each gate's precondition
honest.

### ADR-P3.1-3 — read-only is enforced by a before/after evidence manifest, not by inspection

Rather than auditing each gate's source by eye, `bin/lab-gate-readonly-check <gate>` builds a recursive SHA-256
manifest of the evidence root, runs the gate, rebuilds the manifest, and asserts equality; on mismatch it names the
first changed path and exits non-zero. This makes "read-only" a mechanically re-derived property (tier M), and it will
catch any future gate that regresses into writing evidence — closing the class, not just the two instances. A gate that
legitimately needs a mutable copy writes it under `logs/review/<id>/scratch/`, which is outside the evidence root and
therefore not in the manifest.

### ADR-P3.1-4 — gates are corrected by making them read-only and correctly targeted, never less strict

Every criterion that exists today must still exist and still assert its original property. Where a criterion's
*mechanism* changes (e.g. AC-P2-17 moving from current-evidence copy to scratch copy; AC-P3-18 splitting into
read-only-against-headline plus fixtures-regression), the change is mechanism only; the property asserted is preserved
or strengthened. A machine-readable old→new mapping is recorded (AC-P3.1-13) so the operator can confirm nothing was
quietly dropped. Making a gate green by weakening it is explicitly prohibited and is the one way this tranche can fail
its own review.

## Constitutional change

Article XVI is appended by Z001:

> **Article XVI — Read-only verification gates.** A verification gate (`bin/lab-verify*`, `bin/lab-regression`,
> `bin/lab-gate-readonly-check`, and any future acceptance check) MUST NOT create, modify, move, change the mode of, or
> delete any artefact under the evidence root. It reads evidence and writes only under `logs/review/`. Where a check
> needs a mutable copy of an artefact, it copies into `logs/review/<id>/scratch/` and operates there. Read-only
> behaviour MUST be mechanically enforced (a before/after evidence manifest), not merely asserted. A gate that mutates
> the evidence it certifies is a defect of the same class as a silent test hatch (Article XII).

This sits alongside Article XII (no test hatches in boundary components), Article XIII (verification tiers), Article
XIV (provenance of record) and Article XV (amendment of frozen artefacts) as the fifth lesson learned from review,
each closing a class rather than an instance.

## Task breakdown

| Task | Owns | Closes |
| --- | --- | --- |
| Z001 | Article XVI; ADR-P3.1-1/2/3 | governance + design of record |
| Z002 | `bin/lab-gate-readonly-check`; make every gate read-only; remove the two write paths | D1 |
| Z003 | pinned regression fixtures; `bin/lab-regression`; re-derive `bin/lab-verify-p3` to honest green | D2 |
| Z004 | `bin/lab-verify-p3.1` gate; contract-hash re-verify; old→new criterion mapping; memo update | all |

## Sequencing

Z001 first (principle and the recorded design before any change). Z002 depends on Z001 (it makes gates conform to
Article XVI and provides the enforcement harness). Z003 depends on Z002 (the regression redesign uses the read-only
harness and needs conforming gates). Z004 is the gate and runs last.

```
Z001 -- Z002 -- Z003 -- Z004
```

## Risks

- **A fixture is accidentally a stub, not a real incident.** Mitigated by AC-P3.1-07 requiring each fixture to
  reconcile gaps=0/duplicates=0 through the real `bin/lab-ledger-account`, which a stub cannot do.
- **Re-deriving `bin/lab-verify-p3` weakens a criterion to reach green.** Mitigated by AC-P3.1-13 (old→new mapping,
  each property preserved) and the operator review, which treats a weakened criterion as a tranche failure.
- **Capturing fixtures needs a healthy slot.** Z003 confirms `bin/lab-ready` exit 0 first and waits on `bin/lab-barrier`
  after any reset. Fixtures are captured once and then frozen read-only.
- **The read-only harness itself writes under the evidence root.** Mitigated by ADR-P3.1-3: it writes only its
  manifests under `logs/review/`, and AC-P3.1-04 would catch it (its own run must leave evidence byte-identical).
- **A gate reads `principal` while being "fixed".** Article II still binds; AC-P3.1-15 strips provenance and asserts
  regression + p3 outcomes are unchanged.
