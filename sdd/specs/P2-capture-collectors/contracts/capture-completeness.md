# CONTRACT (FROZEN by C001) — Capture Completeness & the Per-Incident Ledger

**Status:** frozen at end of C001. Hash recorded in `logs/review/C001/`. No later task may change this file.
**Consumers:** P2 `bin/lab-ledger-account`, `bin/lab-query`; P3 analytics (Arm A) and representation builders (Arm B);
the P1 ground-truth oracle. Everything downstream reads a ledger defined here.

This contract defines two things: the exact file set that constitutes a complete incident ledger, and the meaning of
"complete and exactly-once". It does **not** redefine the P1 ledger-integrity invariants (no duplicate LSN within an
incident; ledger LSN range contained by the incident open/close coordinates) — those remain in force and are assumed.

## 1. The per-incident ledger directory

For an incident `<id>`, the ledger lives at `${EVIDENCE_ROOT}/<id>/` on the host and contains exactly:

| File | Producer | Append-only | Purpose |
| --- | --- | --- | --- |
| `db.jsonl` | `bin/lab-consumer` (`pg_recvlogical`+`wal2json`) | yes | DB changes, DDL (via `lab_ddl_audit`), heartbeats — one LSN-ordered stream |
| `snapshots.json` | snapshot loop (C003) | yes (append one object per snapshot) | `{snapshot, wall_clock, lsn}` per ZFS snapshot |
| `fs_diff.tsv` | `zfs diff` walker (C004) | yes (append per snapshot pair) | one row per changed path: `snap_from  snap_to  change_type  path` |
| `fs_hashes.tsv` | tree hasher (C004) | yes (append per snapshot) | `snapshot  path  sha256` over the protected subtree |
| `session.json` | `bin/lab-capture` (C002) | written once at start, closed at stop | manifest of collectors, units/PIDs, output files, open/close coordinates |
| `workload.jsonl` | `bin/lab-capture-workload` (C007) | yes | one object per issued operation (the reconciliation input) |

Derived artefacts (DuckDB views, any Parquet materialisation) are **not** part of the ledger and may be deleted and
rebuilt. The six files above are the store of record.

## 2. Record shapes (the fields the reconciliation and analytics rely on)

### 2.1 `db.jsonl` — one JSON object per line

A **change** record MUST carry at least:

```
{ "kind": "change", "lsn": "<pg_lsn string>", "xid": <int>, "commit_time": "<ISO-8601>",
  "schema": "<schema>", "table": "<relation>", "action": "I|U|D",
  "columns": [ ... new tuple ... ],
  "identity": [ ... OLD tuple; REQUIRED for U and D ... ],
  "principal": "<originating role>" }
```

- For `action` `U` or `D`, `identity` MUST be the full old tuple (guaranteed by `REPLICA IDENTITY FULL`). A missing or
  key-only `identity` on a U/D is a **completeness failure**.
- `principal` is the provenance label. It is present for scoring. It MUST NOT be read by any detection, ranking or
  representation path (Article II); see §5.

A **DDL** record (from `lab_ddl_audit`) MUST carry:

```
{ "kind": "ddl", "lsn": "<pg_lsn string>", "xid": <int>, "commit_time": "<ISO-8601>",
  "command_tag": "CREATE TABLE|ALTER TABLE|DROP TABLE|...", "object_identity": "<schema.relation>",
  "principal": "<originating role>" }
```

A **heartbeat** record MUST carry:

```
{ "kind": "heartbeat", "lsn": "<pg_lsn string>", "wall_clock": "<ISO-8601>" }
```

### 2.2 LSN handling

`lsn` is a PostgreSQL LSN string `X/Y` (hex). All ordering and comparison MUST use the integer value
`(high << 32) + low`, never lexical string order. `3/9` precedes `3/10`; a lexical sort would place `3/10` first and
silently corrupt every range and monotonicity check. Any consumer of this contract MUST use integer LSN comparison.

## 3. Completeness — what "complete" means

An incident ledger is **complete** iff all of the following hold:

- **C-1 Exactly-once coverage.** Every operation in `workload.jsonl` maps to exactly one record in `db.jsonl`
  (for DML/DDL) — no operation is missing (a gap) and no operation appears twice (a duplicate).
- **C-2 Before-images.** Every `U` and `D` change record carries a full `identity` (old tuple).
- **C-3 DDL visibility.** Every DDL operation in the workload appears as a `ddl` record in `db.jsonl`.
- **C-4 Monotonic LSN.** Records in `db.jsonl` are in non-decreasing integer-LSN order.
- **C-5 Heartbeat resolvability.** For any wall-clock time within the incident window, the nearest heartbeat resolves
  an LSN to within **one second**.
- **C-6 Snapshot anchoring.** Every entry in `snapshots.json` has a non-null `lsn`.
- **C-7 Filesystem coverage.** Every path mutated by the workload's filesystem operations appears in `fs_diff.tsv`
  for the snapshot pair spanning the mutation, and `fs_hashes.tsv` reflects the post-change content hash.

## 4. Exactly-once — the mapping rule

`bin/lab-ledger-account` establishes the mapping from each `workload.jsonl` operation to its `db.jsonl` record using
the deterministic key available to **both** sides without reference to provenance:

- DML: `(xid, table, action, natural-key-of-affected-row)` where the natural key is the primary key value carried in
  `columns`/`identity`.
- DDL: `(xid, command_tag, object_identity)`.

A mapping is valid iff it is a bijection over the workload's operations restricted to the ledgerable set (DML + DDL;
heartbeats and snapshots are infrastructure, not workload operations). Gaps and duplicates are both failures.

## 5. Provenance quarantine (Article II, binding on all consumers)

`principal` exists solely so the ground-truth oracle and the scoring path of `lab-ledger-account` can classify a
record as legitimate (`lab_app`) or damage (`lab_agent`). It is a **scoring** attribute. No detection, ranking,
representation or retrieval path — in P2 or any later tranche — may read `principal`. `bin/lab-query`'s default views
MUST exclude it, and `bin/lab-ledger-account`'s coverage/mapping logic MUST NOT reference it. A consumer that reads
`principal` to decide a coordinate has leaked the answer key and its result is void.

## 6. What this contract deliberately does not fix

- The snapshot interval (a tunable, recorded per run; filesystem granularity follows from it — ADR-P2-4).
- The storage/query tool (DuckDB by ADR-P2-2, but the files are the store of record and any reader that honours §2
  is conformant).
- Scenario-specific damage semantics (P2 uses a generic mixed workload — ADR-P2-6).
