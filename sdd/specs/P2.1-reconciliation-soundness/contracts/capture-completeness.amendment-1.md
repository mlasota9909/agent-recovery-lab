# AMENDMENT 1 to CONTRACT `capture-completeness.md` (FROZEN by Y002)

**Status:** frozen by Y002. Envelope `xid` recovered and cross-checked; greedy file-order pairing withdrawn.
Hash recorded in `logs/review/Y002/amendment-1.sha256`. No later task may change this file.
**Supersedes:** `sdd/specs/P2-capture-collectors/contracts/capture-completeness.md` §4 (the exactly-once mapping-key
clause) and the LSN/`xid` field-shape notes in §2.1 to the extent they concern `xid` availability.
**Authorised by:** ADR-P2.1-1, ADR-P2.1-2 (see `plan.md`), under Article XV.
**Original contract:** UNCHANGED and byte-identical. Its C001 hash must continue to verify. This amendment is read
**together with** the original; where they conflict, this amendment governs the superseded clause only.

## A1. Why this amendment exists

`capture-completeness.md` §4 defines the workload-to-ledger mapping key as `(xid, table, action, natural_key)` for DML
and `(xid, command_tag, object_identity)` for DDL. During C008 the consumer parsed only wal2json change records
(`action` I/U/D), which in wal2json 2.6 format-version 2 do not themselves carry `xid`; C008 therefore dropped `xid`
and disambiguated with greedy 1:1 pairing in file order. That substitute is sound only when natural keys are globally
unique. Under the repeated-key concurrency every scenario from P3 onward uses, greedy file-order pairing can mask a
co-occurring gap-and-duplicate on a shared key. This amendment restores `xid` to the key and withdraws the fallback.

## A2. Binding mapping key (supersedes §4)

The mapping from each `workload.jsonl` operation to its `db.jsonl` record is a **bijection** over the ledgerable set
(DML + DDL), keyed on:

- **DML:** `(xid, table, action, natural_key)` — `natural_key` is the primary-key value carried in `columns` (for `I`)
  or `identity` (for `U`/`D`).
- **DDL:** `(xid, command_tag, object_identity)`.

`xid` is the PostgreSQL transaction id, an integer. It MUST be present on both sides (§A3). The key MUST be computable
without reading `principal` (Article II). Greedy file-order pairing MUST NOT appear on the primary mapping path.
Gaps (an unmapped workload op) and duplicates (two ops mapped to one record, or two records claimed by one op) are
both completeness failures and MUST cause a non-zero exit.

## A3. `xid` availability (supersedes the §2.1 `xid` note)

- **DB side (`db.jsonl`).** `bin/lab-consumer` MUST read the wal2json transaction envelope — the begin record
  `{"action":"B","xid":<int>, ...}` — and stamp that `xid` on every `change` and `ddl` record it emits until the
  matching commit record `{"action":"C"}`. Every `change` and `ddl` record MUST therefore carry a non-null integer
  `xid`. Heartbeat records are exempt (they are not transactional workload).
- **Workload side (`workload.jsonl`).** `bin/lab-capture-workload` MUST record, per issued operation, the value of
  `txid_current()` masked to the low 32 bits (to match wal2json's xid width), under the key `xid`.
- **Cross-check.** For any incident, the set of `xid` values on the ledgerable DB records MUST equal the set of `xid`
  values on the corresponding workload operations. A disagreement is a capture failure.

## A4. What this amendment does NOT change

- The ledger file set (§1), all other record shapes (§2.1 apart from the `xid` note), and LSN integer-comparison
  handling (§2.2) are unchanged and remain in force.
- Completeness conditions C-1..C-7 (§3) are unchanged; C-1 (exactly-once coverage) is now evaluated under the
  `xid`-bearing key of §A2.
- The provenance quarantine (§5, Article II) is unchanged and is reinforced: adding `xid` to the key gives the
  mapping a provenance-free disambiguator, removing any temptation to lean on `principal`.
- The deliberately-unfixed items (§6) are unchanged.

## A5. Conformance

A consumer is conformant iff it honours the original contract as amended here: it reads `xid` from both sides, maps by
the §A2 key as a bijection without `principal`, and treats gaps and duplicates as failures. `bin/lab-ledger-account`
is brought into conformance by Y002; the repeated-key soundness of the amended key is proven by Y003.
