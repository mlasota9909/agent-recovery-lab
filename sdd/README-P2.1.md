# SDD Package, Tranche P2.1 (Reconciliation Soundness & Contract Amendment)

Same format as P0, P0.1, P1, P1.1 and P2: **GitHub Spec Kit** layout, extended with a `work-instructions/` tier
below `tasks.md` that Spec Kit itself does not provide.

Unpack so it **merges into** the existing `/home/mlasota/thesis/sdd`. Nothing under any prior `specs/*/` directory is
edited, and — this is the point of the tranche — the frozen `capture-completeness.md` contract stays **byte-identical**
so its recorded hash continues to verify. This tranche repairs one soundness defect found in the P2 acceptance
review and formalises the frozen-contract deviation that produced it.

## Why this tranche exists

P2 delivered the capture pipeline and its gate reported 18/18. Review of the source found the keystone reconciliation
(`bin/lab-ledger-account`, C008) is **sound for the 500-op unique-key acceptance workload but unsound under the
repeated-key concurrency the real experiment runs in**, and that it reached that state by silently deviating from a
frozen contract:

1. **The frozen mapping key was changed by silent substitution.** `capture-completeness.md` §4 defines the
   workload-to-ledger mapping key as `(xid, table, action, natural_key)` for DML and `(xid, command_tag,
   object_identity)` for DDL. wal2json 2.6 (format-version 2) did not emit `xid` on the change records the consumer
   parsed, so C008 dropped `xid` and substituted `(table, action, natural_key)` disambiguated by **greedy 1:1 in file
   order**. This was documented in an observations note, but a frozen contract was changed without a formal amendment
   and without the gate detecting it.

2. **The substitute key is unsound under repeated keys.** With globally-unique natural keys (the C007 workload) the
   mapping is unambiguous and the 500/500, gaps=0, duplicates=0 PASS is valid. But every scenario from P3 onward
   requires concurrent legitimate and malicious traffic that repeats keys — the same row updated twice, a `DELETE` of
   a row inserted earlier in the same incident. When two operations share a key, greedy 1:1 by file order can mask a
   *co-occurring* gap-and-duplicate on that key: two ops, two records, counts balance, so the ledger is reported
   exactly-once when it is actually corrupt. `xid` was the disambiguator that made that failure impossible.

Neither is fraud — the deviation is honestly disclosed in the C008 observations. But the reconciliation is the
instrument that certifies every downstream evidence ledger as trustworthy, so it must be sound **before** any P3
analytics consume scenario data, and the frozen-contract governance hole that let it happen must be closed.

## What P2.1 delivers

| # | Deliverable | Closes |
| --- | --- | --- |
| 1 | New **Article XV** — amendment of frozen artefacts (supersede, never silently deviate or mutate) | The governance class behind the defect |
| 2 | **ADR-P2.1-1** formally recording the §4 deviation, and a superseding, separately-frozen `capture-completeness.amendment-1.md` | The silent deviation |
| 3 | `xid` recovered from the wal2json transaction envelope and cross-validated against workload-side `txid_current()`, restoring the contract's original key; greedy file-order fallback withdrawn | The unsound key |
| 4 | A repeated-key reconciliation soundness test proving the mapping catches a co-occurring gap+duplicate that a count-only check would mask | The soundness risk |
| 5 | `bin/lab-verify-p2.1` gate, P2/P1/P0 contract hashes re-verified unchanged, and an acceptance memo recording that P2 was accepted only after P2.1 | All |

## Target environment

Unchanged and confirmed by the P0/P0.1/P1/P1.1/P2 builds:

- Host `r740core`, Ubuntu 26.04 LTS, KVM, ext4 root. Agent has `sudo`.
- Victim guest `thesisvm01`, keyless SSH from host, agent has `sudo` inside.
- PostgreSQL 18.4, wal2json 2.6-3, ZFS 2.4.1-1ubuntu5, devices `/dev/vdb` + `/dev/vdc` guest-side.
- Deploy root `/home/mlasota/thesis`. Config `etc/lab.env`.
- `bin/lab-verify` 18/18, `bin/lab-verify-p1` 24/24, `bin/lab-verify-p1.1` 16/16, `bin/lab-verify-p2` 18/18, all exit 0.
- `bin/lab-ready` exits 0 (P2 entry gate; still the entry gate here).

## Install

```bash
# on r740core, as mlasota
cd /home/mlasota/thesis
# unpack this package so that it merges into ./sdd
ls sdd/specs/P2.1-reconciliation-soundness/tasks.md   # sanity check
```

## Execute

One task per invocation, in order, dry run first. **Do not batch.**

```bash
cd /home/mlasota/thesis

# read-only dry run, changes nothing
<executor> --print "$(cat sdd/prompts/execute-P2.1.md)

TASK_TO_EXECUTE: Y001
MODE: DRY_RUN"

# then for real
<executor> --force "$(cat sdd/prompts/execute-P2.1.md)

TASK_TO_EXECUTE: Y001
MODE: EXECUTE"
```

Order: `Y001 -> Y002 -> Y003 -> Y004`. `Y004` is the gate and runs last.

## What you review after each task

Open `sdd/specs/P2.1-reconciliation-soundness/work-instructions/WI-Ynnn.md`, read its *Review bundle* and *Operator
review checklist*, then check `/home/mlasota/thesis/logs/review/Ynnn/` exists and its `acceptance.md` rows are
**tier-labelled** per Article XIII. Tick the row in `checklist.md` yourself — the agent does not own the `Reviewed`
column.

The task worth reading line by line is **Y002**, because it decides the binding mapping key that every incident
ledger from P3 onward is certified against, and it is the task that either restores the frozen contract's original
key or proves it cannot be restored.

## Scale note

This tranche is three substantive tasks (Y001 governance + amendment, Y002 the `xid` fix, Y003 the soundness test)
plus the standard gate (Y004), matching the shape of the P0.1 and P1.1 remediations.

## Anti-goals

Do not, in P2.1: mutate `capture-completeness.md` (it stays byte-identical — supersede it with the amendment
instead); change any other frozen contract; add a field to the results row or the ledger-integrity contract; build any
analytics, ranking, representation, retrieval interface, or model call; implement real restore; touch SC-02/03/04
damage logic; read `principal` in any detection, mapping or ranking path. If a task appears to require one of these,
it has been misread.
