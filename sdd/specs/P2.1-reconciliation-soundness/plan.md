# Plan — P2.1: Reconciliation Soundness & Contract Amendment

## Architecture decisions (locked)

### ADR-P2.1-1 — the §4 deviation is recorded, not retro-justified

C008 shipped a mapping key of `(table, action, natural_key)` disambiguated by greedy 1:1 in file order, having found
that wal2json 2.6 did not emit `xid` on the change records it parsed. This ADR records that as a deviation from the
frozen contract `capture-completeness.md` §4, with the wal2json evidence attached, and states the resolution: recover
`xid` from the transaction envelope and restore the contract's original key. The greedy fallback is withdrawn. The
ADR does not pretend the substitute was contract-conformant; it names it a deviation and closes it.

### ADR-P2.1-2 — `xid` is recovered from the transaction envelope, cross-validated workload-side

The most probable root cause of "missing `xid`" is that the consumer parsed only change records (`action` I/U/D) and
discarded the wal2json transaction-envelope records that carry it. In wal2json format-version 2 the begin record
(`{"action":"B","xid":<n>, ...}`) carries the transaction id; every change up to the matching commit
(`{"action":"C"}`) belongs to that `xid`. `bin/lab-consumer` is corrected to read the envelope and stamp `xid` on each
`change` and `ddl` record it writes to `db.jsonl`. Independently, `bin/lab-capture-workload` records `txid_current()`
(masked to the low 32 bits to match wal2json's xid width) per issued operation. Having `xid` on **both** sides makes
the mapping key computable from each side without provenance and gives a cross-check that the two agree. This restores
the frozen contract's original key rather than inventing a new one — the preferred outcome.

**Fallback, only if Y002 proves envelope `xid` genuinely unrecoverable** (documented with evidence): adopt a
workload-issued `op_uid` written into `workload.jsonl` and matched on the DB side via the transaction envelope's
ordering within `xid`; this would require `capture-completeness.amendment-2.md` and is not expected. Y002 must not
reach for the fallback without first exhausting and evidencing the envelope path.

### ADR-P2.1-3 — a frozen contract is amended by supersession, never mutated in place

`capture-completeness.md` is hash-frozen at C001 and its hash is checked by `bin/lab-verify-p2` and will be checked by
every later gate. Editing it — even to correct it — would break that hash chain and every downstream verification, and
would destroy the audit record of what C008 was actually built against. So the correction is expressed as a separate,
sequentially-numbered `capture-completeness.amendment-1.md` that names the §4 clause it supersedes, states the binding
key, and is itself hash-frozen in `logs/review/Y002/`. The original file stays byte-identical. Consumers read the
contract together with its amendments. This is the mechanism Article XV generalises.

### ADR-P2.1-4 — the soundness test uses the experiment's real regime, not the acceptance workload

The C007 unique-key workload cannot exercise the defect, because unique keys make even the greedy heuristic correct.
Y003 therefore builds a small repeated-key workload (the same natural key updated twice; a delete-then-reinsert of one
PK) and proves the mapping is a bijection under it. The load-bearing case is the negative one: inject a co-occurring
gap+duplicate on a shared key — remove one ledger record and duplicate another for the same key so counts still
balance — and prove the `xid`-keyed mapping flags it where a count-only check would report clean. This is the direct
evidence that the reconciliation is sound in the regime P3+ actually runs.

## Constitutional change

Article XV is appended by Y001:

> **Article XV — Amendment of frozen artefacts.** When implementation reveals that a frozen contract cannot be
> honoured exactly as written, the contract MUST NOT be silently deviated from, nor mutated in place. The original
> file MUST remain byte-identical so its recorded hash continues to verify. The change MUST be recorded as a
> superseding amendment: a separate, sequentially-numbered document that names the exact clause it supersedes, is
> itself hash-frozen, and references an ADR stating the technical reason. Every consumer of the contract MUST read the
> contract together with its amendments. A deviation from a frozen contract that is neither reflected in a frozen
> amendment nor caught by the acceptance gate is a defect of the same class as a silent test hatch (Article XII).

This sits alongside Article XII (no test hatches in boundary components), Article XIII (verification tiers) and
Article XIV (provenance of record) as the fourth lesson learned from review, each closing a class rather than an
instance.

## Task breakdown

| Task | Owns | Closes |
| --- | --- | --- |
| Y001 | Article XV; ADR-P2.1-1; opens the amendment | D1 governance class |
| Y002 | `xid` recovery (consumer + workload); withdraw greedy fallback; freeze amendment-1 | D1 + D2 root cause |
| Y003 | repeated-key reconciliation soundness test + negative case | D2 proof |
| Y004 | `bin/lab-verify-p2.1` gate; contract hash re-verify; memo update | all |

## Sequencing

Y001 first (principle and the formal deviation record before the fix). Y002 depends on Y001 (it freezes the amendment
the principle authorises, and restores the key). Y003 depends on Y002 (it proves the corrected key sound). Y004 is the
gate and runs last.

```
Y001 -- Y002 -- Y003 -- Y004
```

## Risks

- **`xid` from the envelope disagrees with `txid_current()` width.** wal2json emits a 32-bit xid; `txid_current()`
  returns a 64-bit epoch-extended value. Y002 masks the workload-side value to the low 32 bits before comparing.
  Recorded here so the agent does not treat the width mismatch as a disagreement.
- **Re-capturing to get `xid` needs a healthy slot.** Y002 must confirm `bin/lab-ready` exit 0 first, and after any
  reset wait on `bin/lab-barrier`. The C007 workload is re-run for verification only; it is not experimental data.
- **A future agent edits `capture-completeness.md` to "apply" the amendment.** Mitigated by Article XV and by AC-P2.1-02
  asserting the original file is byte-identical; the gate fails if it is touched.
- **Fallback creep.** Y002 could jump to the `op_uid` fallback rather than doing the envelope work. The WI requires the
  envelope path to be exhausted and evidenced before the fallback is even considered, and ADR-P2.1-2 marks the
  fallback not-expected.
