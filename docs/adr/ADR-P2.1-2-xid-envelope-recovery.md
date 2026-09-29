# ADR-P2.1-2 — Recover xid from the wal2json transaction envelope

Status: accepted at P2.1; indexed at P8 close-out.

The capture-completeness amendment requires the original `(xid, table, action, natural_key)` mapping key. wal2json
format-version 2 places `xid` on the transaction begin envelope rather than each change record. The consumer therefore
stamps the envelope xid onto its enclosed changes, while the workload records `txid_current()` low bits. The two sides
are cross-checked and mapped bijectively. Greedy file-order pairing is withdrawn. This file indexes the decision
already recorded in the P2.1 plan and Y002 evidence; it does not change the frozen amendment.
