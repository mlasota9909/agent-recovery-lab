# Spec — P3.1: Gate Integrity (Read-Only Verification & Regression Redesign)

**Feature ID:** P3.1-gate-integrity
**Status:** ready for implementation
**Owner:** Maciej Lasota
**Depends on:** P3 (accepted, pending this remediation)
**Blocks:** P4 (restore + validation) — P4 relies on the regression signal to know prior instruments are intact; that signal must be meaningful and achievable first

## 1. Purpose

Make every verification gate strictly read-only over the evidence tree, and replace the structurally-impossible
nested regression with one that runs each prior gate against its own pinned healthy fixture. Restore `bin/lab-verify-p3`
to an honest green under the redesign. Add the constitutional principle that stops a gate from ever again mutating the
evidence it certifies. This tranche builds no intelligence and changes no frozen contract.

## 2. Problem statement

**D1 — verification gates mutate the evidence they check.** `bin/lab-verify-p1.1` crashed at the P3 nested re-run
with `PermissionError` writing the frozen `db.jsonl` (mode 0444). `bin/lab-verify-p2` (criterion AC-P2-17) copies a
frozen `db.jsonl` onto the **current** evidence tree as part of its check. A gate that writes to evidence can corrupt
the artefact a later gate certifies, can fail for reasons unrelated to the code under test, and violates the
separation between "measuring" and "changing" that the whole audit chain depends on. The P2 review flagged this once;
it has now recurred, so it is a class, not an instance.

**D2 — the nested regression is structurally impossible to pass green.** `AC-P3-18` re-runs the five prior gates
against `archive/current` pointed at the **frozen** SC-01 headline incident, and `AC-P2-17` / `AC-P2.1-13` chain the
same idea. But the headline ledger must be frozen (consumer stopped) to hold a stable state for oracle scoring, while
`bin/lab-verify` (P0) *requires* a live capture state: consumer active, slot draining, retained WAL below threshold.
Those two conditions cannot both hold, so the nested re-run is guaranteed red for **state** reasons regardless of
whether the prior code is correct. The regression *intent* — "prove prior instruments still work" — is valid and must
be preserved; the *implementation* conflates "is the code correct?" with "is the lab in the live state P0 expects?"

## 3. Scope

### In scope

- **Article XVI** added to the constitution: verification gates are strictly read-only over the evidence root.
- **ADR-P3.1-1** recording D1 and D2; **ADR-P3.1-2** the pinned-fixture regression design; **ADR-P3.1-3** the
  read-only enforcement mechanism.
- Making every `bin/lab-verify*` strictly read-only over evidence: removing the `lab-verify-p1.1` write that caused
  the `PermissionError`, and reworking `lab-verify-p2` AC-P2-17 so it no longer copies onto current evidence (it
  operates on a copy under `logs/review/<id>/scratch/`). No gate creates, modifies, moves, chmods or deletes anything
  under the evidence root.
- A **read-only enforcement harness** (`bin/lab-gate-readonly-check`) that runs a named gate and asserts the evidence
  tree is byte-identical before and after (recursive hash manifest compared), used by the P3.1 gate against every
  prior gate.
- A **pinned healthy regression fixture** per prior tranche (a real, captured, reconciled incident held read-only
  under `fixtures/regression/`), and a redesigned regression (`bin/lab-regression`) that runs each prior gate against
  its own fixture in a live-equivalent state, replacing the against-frozen-headline re-run.
- Retargeting the P3 regression criterion: the against-headline portion is narrowed to **read-only** contract-hash and
  code-level assertions (hashes unchanged, gate scripts present and read-only), while the "prior code still works"
  portion is delegated to `bin/lab-regression` against fixtures. Any change to an earlier gate's criterion meaning is
  recorded by ADR + superseding note per Article XV; the frozen contract files stay byte-identical.
- `bin/lab-verify-p3.1` gate; a re-derived `bin/lab-verify-p3` that reaches honest green under the redesign; an
  acceptance memo recording that P3 was accepted only after P3.1.

### Out of scope

- Any change to a frozen contract (`candidate-coordinate.md`, `arm-coordinate.md`, `capture-completeness.md`,
  `capture-completeness.amendment-1.md`, results-row, ledger-integrity, P0/P1 contracts).
- Any new field on any contract.
- Any restore, representation, retrieval interface, or model invocation (P4+).
- Re-fitting the Arm A ranker or the naive comparator, or re-running the SC-01 headline to change its numbers. The
  headline incident is preserved as-is; P3.1 only stops gates from mutating it and stops mis-targeting it.
- SC-02/03/04 damage semantics.
- Making any criterion pass by weakening what it checks.

## 4. Functional requirements

- **FR-1 Read-only principle.** The constitution gains Article XVI: a verification gate MUST NOT create, modify,
  move, change the mode of, or delete any artefact under the evidence root; it reads evidence and writes only under
  `logs/review/`. A gate that needs a mutable copy makes it under `logs/review/<id>/scratch/`. A gate that mutates
  evidence is a defect of the same class as a silent test hatch (Article XII).
- **FR-2 Gates are read-only.** Every `bin/lab-verify*` is read-only over the evidence root. The `lab-verify-p1.1`
  frozen-`db.jsonl` write is removed; `lab-verify-p2` AC-P2-17 operates on a scratch copy, never on current evidence.
- **FR-3 Read-only enforcement harness.** `bin/lab-gate-readonly-check <gate>` builds a recursive SHA-256 manifest of
  the evidence root, runs the named gate, rebuilds the manifest, and asserts they are identical; it exits non-zero and
  names the first changed path if not.
- **FR-4 Pinned regression fixtures.** For each prior tranche that a gate verifies, a real captured+reconciled
  incident is held read-only under `fixtures/regression/<tranche>/` with a manifest and provenance note. Fixtures are
  synthetic lab data (Article X). A fixture is never the live headline incident.
- **FR-5 Redesigned regression.** `bin/lab-regression` runs each prior gate against its own pinned fixture placed in
  the live-equivalent state that gate expects, and reports per-gate PASS/FAIL with per-tier totals. This is the
  "prior code still works" signal. It does not touch the headline incident.
- **FR-6 Retargeted P3 regression criterion.** `bin/lab-verify-p3` is re-derived so its regression criterion has two
  parts: (a) read-only assertions against the headline (all frozen contract hashes unchanged; every gate script
  present and passes `bin/lab-gate-readonly-check`); (b) `bin/lab-regression` green across all prior gates. Under this
  redesign `bin/lab-verify-p3` reaches an honest green with per-tier totals. Any earlier-criterion meaning change is
  recorded per Article XV; frozen files stay byte-identical.
- **FR-7 Gate and memo.** `bin/lab-verify-p3.1` runs every P3.1 criterion with per-tier totals; re-verifies all prior
  contract hashes unchanged; runs `bin/lab-gate-readonly-check` against every `bin/lab-verify*`; runs `bin/lab-regression`;
  and the acceptance memo records the remediation and "P3 accepted only after P3.1".

## 5. Acceptance criteria

| ID | Tier | Requirement |
| --- | --- | --- |
| AC-P3.1-01 | M | `constitution.md` contains a well-formed Article XVI (read-only verification gates); article count is 16 |
| AC-P3.1-02 | M | ADR-P3.1-1 records D1 (gate writes to evidence) and D2 (impossible nested regression) with the D010 evidence; ADR-P3.1-2 and ADR-P3.1-3 record the fixture design and the enforcement mechanism |
| AC-P3.1-03 | M | `bin/lab-gate-readonly-check <gate>` exists: builds an evidence manifest, runs the gate, rebuilds, asserts byte-identical; exits non-zero naming the first changed path otherwise |
| AC-P3.1-04 | M | Running `bin/lab-gate-readonly-check` against each of `lab-verify`, `-p1`, `-p1.1`, `-p2`, `-p2.1`, `-p3` leaves the evidence root byte-identical (manifest before == after) |
| AC-P3.1-05 | M | The `lab-verify-p1.1` write path that caused `PermissionError` on a 0444 `db.jsonl` is removed; the gate runs to completion read-only |
| AC-P3.1-06 | M | `lab-verify-p2` AC-P2-17 no longer copies onto current evidence; it operates on a copy under `logs/review/`, and current evidence is unchanged by the run |
| AC-P3.1-07 | M | A pinned regression fixture exists per prior tranche under `fixtures/regression/<tranche>/`, each a real captured+reconciled incident (reconciles gaps=0, duplicates=0) held read-only, with a provenance note |
| AC-P3.1-08 | M | `bin/lab-regression` runs each prior gate against its own fixture and reports per-gate PASS with per-tier totals, exit 0 |
| AC-P3.1-09 | M | A deliberately broken prior gate (in scratch) makes `bin/lab-regression` report that gate FAIL and exit non-zero (the signal is real) |
| AC-P3.1-10 | M | `bin/lab-verify-p3` re-derived: regression criterion split into read-only against-headline assertions + `bin/lab-regression`; gate reaches honest green with per-tier totals, exit 0 |
| AC-P3.1-11 | M | The SC-01 headline incident is byte-identical to its P3 close (hash of its `db.jsonl` and results rows unchanged); P3.1 did not alter the headline numbers |
| AC-P3.1-12 | M | No frozen contract changed: P0/P1/P2/P2.1/P3 contract hashes all re-verify (incl. `capture-completeness.md`) |
| AC-P3.1-13 | M | Every criterion in every gate is at least as strict as before (no criterion removed or weakened; a mapping of old→new is recorded and each mapped criterion still asserts its original property) |
| AC-P3.1-14 | M | `bin/lab-verify-p3.1` reports every criterion PASS with per-tier totals printed separately, exit 0 |
| AC-P3.1-15 | M | Provenance-blindness preserved: the redesign reads no `principal` in any detection/mapping path (a strip leaves regression + p3 outcomes unchanged) |
| AC-P3.1-16 | A | `docs/p3-acceptance-memo.md` records the two remediated defects and `p3_accepted_only_after: "P3.1"` on machine-readable fields |

All criteria are tier M except AC-P3.1-16, which attests a one-time documentation event and still asserts on JSON
fields, per Article XIII.

## 6. Definition of done

`bin/lab-verify-p3.1` green with per-tier totals; Article XVI in force; every `bin/lab-verify*` proven read-only over
evidence by `bin/lab-gate-readonly-check`; the two known write paths removed; pinned regression fixtures in place;
`bin/lab-regression` green across all prior gates and demonstrably able to go red; `bin/lab-verify-p3` re-derived to an
honest green; the SC-01 headline byte-identical to its P3 close; all frozen contract hashes unchanged; no criterion
weakened; acceptance memo updated.
