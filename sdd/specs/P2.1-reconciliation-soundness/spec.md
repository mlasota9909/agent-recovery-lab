# Spec — P2.1: Reconciliation Soundness & Contract Amendment

**Feature ID:** P2.1-reconciliation-soundness
**Status:** ready for implementation
**Owner:** Maciej Lasota
**Depends on:** P2 (accepted, pending this remediation)
**Blocks:** P3 (derived analytics + Arm A ranker) — P3 must not consume scenario ledgers until the reconciliation is proven sound under repeated keys (Y003)

## 1. Purpose

Make the keystone reconciliation (`bin/lab-ledger-account`) sound under the repeated-key concurrency the real
experiment runs in, restore fidelity to the frozen `capture-completeness.md` §4 mapping key, and add the
constitutional principle and amendment mechanism that stop a frozen contract from ever again being deviated from
silently. This tranche builds no intelligence and changes no frozen contract in place.

## 2. Problem statement

**D1 — silent deviation from a frozen contract.** `capture-completeness.md` §4 (frozen at C001) defines the
workload-to-ledger mapping key as `(xid, table, action, natural_key)` for DML and `(xid, command_tag,
object_identity)` for DDL. wal2json 2.6 (format-version 2) did not emit `xid` on the change records that
`bin/lab-ledger-account` (C008) parsed, so C008 dropped `xid` and substituted `(table, action, natural_key)`
disambiguated by greedy 1:1 in file order. The substitution was recorded in the C008 observations note, but a frozen
contract was changed without a formal amendment and the P2 gate did not detect the divergence. There is currently no
mechanism, constitutional or mechanical, that forbids or catches this.

**D2 — the substitute key is unsound under repeated keys.** For the C007 acceptance workload the natural keys are
globally unique, so `(table, action, natural_key)` is unambiguous and the 500/500, gaps=0, duplicates=0 PASS is
valid. But every scenario from P3 onward requires concurrent legitimate and malicious activity that repeats keys —
the same row updated twice, a `DELETE` of a row inserted earlier in the same incident. When two operations share a
key, greedy 1:1 by file order can pair a workload op to the wrong ledger record, masking a co-occurring
gap-and-duplicate: two ops, two records, counts balance, and the ledger is reported exactly-once when it is corrupt.
`xid` was the disambiguator that made this class of error impossible, and it is gone.

## 3. Scope

### In scope

- **Article XV** added to the constitution: amendment of frozen artefacts (supersede, never silently deviate or
  mutate in place).
- **ADR-P2.1-1** formally recording the §4 deviation, and a superseding, separately-frozen
  `capture-completeness.amendment-1.md` that names the exact clause it supersedes and references the ADR. The original
  `capture-completeness.md` stays **byte-identical**; its C001 hash must keep verifying.
- Recovering `xid` on the DB side of the ledger from the **wal2json transaction envelope** (the `B`/begin record
  carries `xid`; propagate it to every change until the matching `C`/commit), cross-validated against a workload-side
  `txid_current()` recorded per operation in `workload.jsonl`. This restores the contract's original mapping key.
- Withdrawing the greedy file-order fallback from `bin/lab-ledger-account` as the primary mechanism; the mapping
  becomes a bijection keyed on `(xid, table, action, natural_key)` / `(xid, command_tag, object_identity)`, computed
  without reference to `principal`.
- A **repeated-key reconciliation soundness test**: a workload that reuses natural keys within one incident, with a
  negative case proving the mapping detects a co-occurring gap+duplicate that a count-only check would miss.
- `bin/lab-verify-p2.1`: the tiered gate for this tranche, re-verification that the P0/P1/P2 contract hashes are
  unchanged (including `capture-completeness.md`), and an updated acceptance memo recording that P2 was accepted only
  after P2.1.

### Out of scope

- Mutating `capture-completeness.md` or any other frozen contract in place.
- Any new field on the results row or the ledger-integrity contract.
- Any analytics, ranking, representation, retrieval interface, or model invocation (P3+).
- Real point-in-time restore or restored-state validation (P4).
- SC-02/03/04 damage semantics.
- Re-running historical incidents; the C007 acceptance incident is re-reconciled under the corrected key, not
  re-blessed as experimental data.

## 4. Functional requirements

- **FR-1 Amendment principle.** The constitution gains Article XV: a frozen contract that cannot be honoured as
  written must be amended by a superseding, separately-frozen document referencing an ADR; the original file must stay
  byte-identical and continue to verify; consumers read the contract together with its amendments; an undetected,
  un-amended deviation from a frozen contract is a defect of the same class as a silent test hatch.
- **FR-2 Formal amendment.** `capture-completeness.amendment-1.md` supersedes §4's mapping-key clause, states the
  binding key, records that the greedy file-order fallback is withdrawn, and is hash-frozen in `logs/review/Y002/`.
  ADR-P2.1-1 states the technical reason. The original contract file is unchanged and its C001 hash re-verifies.
- **FR-3 `xid` recovery.** `bin/lab-consumer` captures `xid` from the wal2json transaction envelope and stamps it on
  every `change` and `ddl` record in `db.jsonl`. `bin/lab-capture-workload` records `txid_current()` (masked to the
  32-bit xid) per issued operation in `workload.jsonl`. The two `xid` sources agree for the acceptance workload.
- **FR-4 Sound mapping.** `bin/lab-ledger-account` maps each workload operation to its ledger record by
  `(xid, table, action, natural_key)` (DML) / `(xid, command_tag, object_identity)` (DDL), as a bijection over the
  ledgerable set, computed without reading `principal`. The greedy file-order heuristic is removed from the primary
  path. Gaps and duplicates remain failures.
- **FR-5 Repeated-key soundness.** A soundness test exercises a workload that repeats natural keys within an incident
  and proves: (a) the full ledger reconciles as a clean bijection; (b) a deliberately injected co-occurring
  gap+duplicate on a shared key is **detected** (not masked); (c) the ledger reconciles clean again after the fault is
  reverted.
- **FR-6 Gate and memo.** `bin/lab-verify-p2.1` runs every P2.1 acceptance check with per-tier totals; re-verifies the
  P0/P1/P2 contract hashes unchanged including `capture-completeness.md`; confirms `bin/lab-verify-p2` still 18/18; and
  the acceptance memo records the remediation and the "accepted only after P2.1" statement.

## 5. Acceptance criteria

| ID | Tier | Requirement |
| --- | --- | --- |
| AC-P2.1-01 | M | `constitution.md` contains a well-formed Article XV (amendment of frozen artefacts); article count is 15 |
| AC-P2.1-02 | M | `capture-completeness.md` is byte-identical to its C001 freeze; its recorded hash re-verifies |
| AC-P2.1-03 | M | `capture-completeness.amendment-1.md` exists, names the §4 clause it supersedes, references ADR-P2.1-1, and is hash-frozen in `logs/review/Y002/` |
| AC-P2.1-04 | M | ADR-P2.1-1 records the deviation (dropped `xid`, greedy file-order fallback) and the resolution, with the wal2json evidence |
| AC-P2.1-05 | M | Every `change` and `ddl` record in a freshly captured `db.jsonl` carries a non-null integer `xid` |
| AC-P2.1-06 | M | Every operation in a freshly captured `workload.jsonl` carries a `txid_current()`-derived `xid`; the workload-side and DB-side `xid` sets agree for the acceptance workload |
| AC-P2.1-07 | M | `bin/lab-ledger-account` maps by the `xid`-bearing key; a `grep` shows no greedy file-order pairing remains on the primary path |
| AC-P2.1-08 | M | The mapping/coverage logic does not reference `principal` (Article II); a provenance-strip leaves the mapping unchanged |
| AC-P2.1-09 | M | On the C007 unique-key acceptance workload, reconciliation still reports ops=500, mapped=500, gaps=0, duplicates=0 under the new key |
| AC-P2.1-10 | M | On a repeated-key workload, the full ledger reconciles as a clean bijection (gaps=0, duplicates=0) |
| AC-P2.1-11 | M | A co-occurring gap+duplicate injected on a shared natural key is **detected** (reconciliation reports non-zero gaps and duplicates and exits non-zero) |
| AC-P2.1-12 | M | After reverting the injected fault, the repeated-key ledger reconciles clean again |
| AC-P2.1-13 | M | `bin/lab-verify-p2` still reports 18/18, exit 0, under the corrected consumer and reconciliation |
| AC-P2.1-14 | M | `bin/lab-verify-p2.1` reports every criterion PASS with per-tier totals printed separately, exit 0 |
| AC-P2.1-15 | M | P0 (R007), P1 (W002/W010) and P2 (C001) contract hashes are unchanged |
| AC-P2.1-16 | A | `docs/p2-acceptance-memo.md` records the remediated defect and the statement that P2 was accepted only after P2.1 (asserted on machine-readable fields) |

All criteria are tier M except AC-P2.1-16, which attests a one-time documentation event and still asserts on JSON
fields, per Article XIII.

## 6. Definition of done

`bin/lab-verify-p2.1` green with per-tier totals; Article XV in force; `capture-completeness.md` byte-identical and
re-verifying; `capture-completeness.amendment-1.md` frozen; `xid` recovered on both ledger sides and cross-validated;
`bin/lab-ledger-account` sound under repeated keys with the greedy fallback withdrawn; the repeated-key soundness test
detecting a masked corruption; `bin/lab-verify-p2` still 18/18; prior contract hashes unchanged; acceptance memo
updated.
