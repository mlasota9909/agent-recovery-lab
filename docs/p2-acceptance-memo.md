# P2 acceptance memo

P2 capture collectors were provisionally green at C010. Reconciliation soundness under repeated keys was not
proven until P2.1. This memo records that P2 is accepted **only after** that remediation.

```json
{
  "reconciliation_key_deviation": "C008 mapped on (table, action, natural_key) with greedy 1:1 in file order after wal2json v2 omitted xid on change records; capture-completeness.md §4 required (xid, table, action, natural_key).",
  "xid_recovered_from_envelope": true,
  "amendment": "capture-completeness.amendment-1.md",
  "amendment_ref": "sdd/specs/P2.1-reconciliation-soundness/contracts/capture-completeness.amendment-1.md",
  "adr": "ADR-P2.1-1",
  "p2_accepted_only_after": "P2.1",
  "capture_completeness_mutated": false,
  "article_xv": true
}
```

## Status

- Frozen `capture-completeness.md` is byte-identical to its C001 hash.
- `capture-completeness.amendment-1.md` supersedes §4: mapping key includes envelope `xid`.
- `bin/lab-ledger-account` is a bijection on that key and does not read `principal`.
- Repeated-key soundness: clean bijection; co-occurring gap+duplicate on a shared key is detected; clean after revert.
- Gate: `bin/lab-verify-p2.1`.
