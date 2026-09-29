# ADR-P2.1-1 — Silent deviation from `capture-completeness.md` §4

**Status:** accepted  
**Date:** 2026-08-24  
**Tranche:** P2.1  
**Authorises:** `sdd/specs/P2.1-reconciliation-soundness/contracts/capture-completeness.amendment-1.md` under Article XV  
**Related:** ADR-P2.1-2 (`xid` recovered from the wal2json transaction envelope)

This ADR records a deviation. It does not retro-justify it.

## Frozen clause (verbatim)

From `sdd/specs/P2-capture-collectors/contracts/capture-completeness.md` §4, frozen at C001, hash
`59aeaa61281f211046b953a0641de72dc55c3f6cecc7278ee45802d41003d647`:

```
## 4. Exactly-once — the mapping rule

`bin/lab-ledger-account` establishes the mapping from each `workload.jsonl` operation to its `db.jsonl` record using
the deterministic key available to **both** sides without reference to provenance:

- DML: `(xid, table, action, natural-key-of-affected-row)` where the natural key is the primary key value carried in
  `columns`/`identity`.
- DDL: `(xid, command_tag, object_identity)`.

A mapping is valid iff it is a bijection over the workload's operations restricted to the ledgerable set (DML + DDL;
heartbeats and snapshots are infrastructure, not workload operations). Gaps and duplicates are both failures.
```

## What C008 shipped instead

`bin/lab-ledger-account` (C008) dropped `xid` from both keys and substituted greedy 1:1 pairing in file order:

- DML: `(table, action, natural_key)`
- DDL: `(command_tag, object_identity)`

Implementation (comments in `lib/lab_ledger_account.py`):

```
# Greedy 1:1 in file order. Multiple UPDATEs of the same id are distinct ops
# (contract §4 also names xid; wal2json v2 did not emit xid, so order+key is
# the deterministic stand-in). Does not read principal.
```

Mapping-sample keys in `logs/review/C008/mapping-sample.md` are of the form
`['DML', 'p2_probe', 'I', 17000000]` — no `xid` component.

C008 recorded this only in `logs/review/C008/observations.md`:

> Mapping is a greedy 1:1 in file order on `(table, action, natural_key)` for DML
> and `(command_tag, object_identity)` for DDL. wal2json v2 did not emit `xid`
> despite `-o include-xids=true`; order+key is the deterministic stand-in for
> contract §4's xid component.
>
> xid not present on-stream; greedy mapping used instead. 500/500 still holds.

The original contract file was not amended. The P2 gate (`bin/lab-verify-p2`) did not detect the divergence.
That is the governance failure Article XV now forbids.

## wal2json evidence

`bin/lab-consumer` already passes `-o include-xids=true` `-o format-version=2`. C008 parsed only change
records (`action` I/U/D). Observed shape of those records in the C008-era window of
`evidence/SC-01/SC-01_20260820T051544Z/db.jsonl` (fields other than `columns` omitted):

```
{"action": "I", "lsn": "0/413C3FA0", "pk": [{"name": "id", "type": "bigint"}],
 "schema": "public", "table": "orders", "timestamp": "2026-08-20 05:15:59.63876+00"}
```

Keys present: `action`, `columns`, `lsn`, `pk`, `schema`, `table`, `timestamp`. **No `xid`.**

Begin-envelope records in the same window also lacked `xid`:

```
{"action": "B", "lsn": "0/41003590", "nextlsn": "0/410035C0",
 "timestamp": "2026-08-20 05:15:50.967707+00"}
```

Later catch-up records in the same file (2026-08-21, after C009 slot recovery) do carry `xid` on `B` and `I`:

```
{"action": "B", "lsn": "0/45009938", "nextlsn": "0/45009968",
 "timestamp": "2026-08-21 06:02:21.816964+00", "xid": 6141}
```

So `xid` is not an invented field: the plugin can emit it on the transaction envelope. C008 never consumed
the envelope, observed its absence on change records, and substituted a different key.

## Soundness consequence

The substitute key is a bijection only when natural keys are globally unique within `(table, action)` for
the incident. The C007 acceptance workload uses unique keys, so 500/500, gaps=0, duplicates=0 is valid for
that workload.

Every scenario from P3 onward repeats keys: the same row updated twice, a `DELETE` of a row inserted
earlier in the same incident, interleaved `lab_app` / `lab_agent` traffic on a shared primary key. Under
that regime, greedy 1:1 by file order can pair a workload op to the wrong ledger record and mask a
co-occurring gap-and-duplicate: two ops, two records, counts balance, the ledger is reported exactly-once
while it is corrupt. `xid` was the disambiguator that made that class of error impossible.

## Resolution

1. Record the deviation here. Do not pretend the substitute was contract-conformant.
2. Recover `xid` from the wal2json transaction envelope and stamp it on every `change`/`ddl` record;
   record `txid_current()` (low 32 bits) per workload op (ADR-P2.1-2). Restore the frozen key.
3. Withdraw greedy file-order pairing from the primary mapping path.
4. Amend by supersession: `capture-completeness.amendment-1.md` names §4 as the superseded clause, is
   itself hash-frozen by Y002, and is read together with the original. The original file stays
   byte-identical so its C001 hash continues to verify (Article XV).
5. Prove the restored key sound under repeated keys (Y003).

Fallback to a workload-issued `op_uid` is not authorised by this ADR. That path requires
`capture-completeness.amendment-2.md` and operator sign-off if and only if Y002 proves envelope `xid`
genuinely unrecoverable.
