# Contract (FROZEN once L002 lands) — incident-isolation

**Status:** frozen at L002 close. Hash recorded in `logs/review/L002/`. New contract, not an edit of any prior file.
**Owner:** P7.1. **Consumed by:** the matrix orchestrator (`lib/lab_matrix.py`), `bin/lab-reset`, `bin/lab-coordinate`,
and every future multi-incident tranche.

## 1. Purpose

Guarantee that operating on one experimental unit (incident) cannot destroy or alter the recorded state of another,
when many incidents share the ZFS pool `labpool`. This is the fix for the P7 root cause: T012 `zfs rollback -r` on the
shared parent `labpool/victim` destroyed sibling incidents' snapshots.

## 2. Dataset layout (normative)

Each incident owns a dataset subtree, created fresh at generation:

```
labpool/victim/inc_<incident_id>            # incident root (no direct data)
labpool/victim/inc_<incident_id>/pgdata     # this incident's PostgreSQL data directory
labpool/victim/inc_<incident_id>/protected  # this incident's protected filesystem subtree
```

- `<incident_id>` is the existing join key (e.g. `i_20260826T095506Z_62a9e9`), never a scenario name.
- The shared parent `labpool/victim` MUST NOT hold a live `pgdata`/`protected` used by the matrix. It is a container
  only. Any pre-existing shared `labpool/victim/pgdata` used before P7.1 is left byte-untouched for SC-01 provenance;
  the matrix re-run does not use it.
- Snapshots (`pre_injection`, `post_capture`, and any T-tier snapshots) are taken **on the incident subtree**:
  `labpool/victim/inc_<id>@pre_injection`, etc. They are siblings-isolated by construction.

## 3. Cluster model (normative)

- One incident cluster is live at a time. The cluster for incident X is started against
  `labpool/victim/inc_<id>/pgdata` on a per-incident port/socket, and stopped at teardown. Isolation is at the
  **dataset** level (persistent across cluster stop/start); the cluster is transient.
- `bin/lab-coordinate --lsn/--time` for incident X MUST resolve against incident X's own live cluster heartbeat table.
  Resolving X's coordinate against a different incident's cluster is prohibited (this was the D2 failure mode).

## 4. Reset semantics (normative) — supersedes T012 usage for multi-incident runs

- Reset for incident X operates **only** on `labpool/victim/inc_<id>` and its children:
  - `t1` = `zfs rollback labpool/victim/inc_<id>/pgdata@pre_injection` (+ `protected@pre_injection`), non-recursive on
    each leaf, or `-r` scoped to `labpool/victim/inc_<id>` — **never** `-r` on `labpool/victim`.
  - `t2` = rollback to `@post_capture` on the incident subtree.
- `bin/lab-reset` MUST refuse, with a non-zero exit, any invocation whose target resolves to `labpool/victim` (the
  shared parent) or to a dataset outside the named incident's subtree. This refusal is the enforcement of the invariant
  in section 5.
- SC-01 is exempt from re-run entirely (its headline is banked); reset MUST refuse to operate on the SC-01 incident.

## 5. Isolation invariant (the property L002 must prove)

> Given two incidents A and B, each with `@pre_injection` and `@post_capture` snapshots on their own subtrees,
> performing any reset (`t1`/`t2`) or teardown on A leaves **every** snapshot of B, and B's `pgdata`/`protected`
> contents and heartbeat table, byte-identical.

Proven by the L002 negative test: create A and B, hash B's snapshot list and a heartbeat digest, reset/teardown A,
re-hash B — must be identical; then attempt `zfs rollback -r labpool/victim@…` and confirm `bin/lab-reset` refuses it.

## 6. Teardown (normative)

- Teardown of incident X destroys only `labpool/victim/inc_<id>` (recursively within that subtree). It MUST NOT touch
  any sibling subtree or the shared parent's other children.
- The incident's evidence ledger, sealed `db.jsonl`, results rows and archive record live on the host outside the pool
  (unchanged from P2) and are retained after teardown.

## 7. Coordinate resolution (normative for re-run cells)

- Re-run matrix cells MUST resolve coordinates **live** against the incident's own cluster
  (`resolved_by: live_heartbeat`), producing a real `skew_ms`. The archive `snapshot_first` path
  (`LAB_P7_HOST_COORD=1`) is **prohibited** for a re-run cell that has a live incident cluster, and is retained only
  for the banked SC-01 rows already written.

## 8. What this contract does not change

- The results-row schema and its `reset_tier` enum (`t0|t1|t2`) are unchanged.
- P4 restore+validate, the representations, the Arm B harness, the model pin, and all prior frozen contracts are
  unchanged.
- ZFS/PostgreSQL native mechanisms only; no new dependency (Article V).

## 9. Runtime selection (normative) — added by L002 architecture decision

Per-incident isolation is only real if **every** stateful command resolves the current incident's values, not the flat
globals in `etc/lab.env` (`PG_DATA`, `PG_PORT`, `DS_PARENT`, and SC-02's hardcoded `/srv/protected`). Changing only
`lab-reset`, generation and `lab-coordinate` would leave snapshot-tick, heartbeat, logical decoding/consumer, filesystem
capture and the SC-02 scenario operating on the shared legacy substrate. Therefore:

- **Incident runtime record.** Generation writes `runtime/incidents/<id>.env` (host-side, outside the pool) containing at
  least: `INC_ID`, `INC_DS=labpool/victim/inc_<id>`, `INC_PGDATA`, `INC_PROTECTED` (the `protected` dataset's own
  mountpoint), `INC_PG_PORT`, `INC_PG_SOCKET`, `INC_SLOT`, `INC_HEARTBEAT_PORT`. Values are unique per incident; SC-01's
  record is not created (it is exempt/banked).
- **One selection helper.** `lib/lab_incident_env.sh` is sourced **after** `etc/lab.env` by every command that touches
  incident state: generation, `lab-reset`, `lab-coordinate`, the snapshot ticker, the heartbeat writer, the logical
  consumer, filesystem/DB capture, and the scenario drivers (incl. SC-02). It resolves the active incident (explicit
  `--incident <id>` or `LAB_ACTIVE_INCIDENT`) and exports the `INC_*` values, which override the flat globals for that
  process only. `etc/lab.env` is not edited.
- **Filesystem-path decision (normative).** Scenario filesystem targets are **incident-derived**: SC-02 and any
  filesystem scenario read `INC_PROTECTED`, never a hardcoded `/srv/protected`. A missing/unset `INC_PROTECTED` is a hard
  refusal, not a fallback to the shared path.
- **Non-regression.** SC-01's banked rows and ledger used the flat globals and are left byte-untouched; the helper is
  only consulted for re-run incidents that have a runtime record.

## 10. Negative-test target (normative) — added by L002 architecture decision

The D1 reproduction MUST NOT run the old descendant-enumerating reset over live `labpool/victim` (that scope contains the
banked SC-01 `pgdata`/`protected`). Instead:

- Create a disposable parent `labpool/p7_1_negative` with two throwaway incident subtrees A and B (each with snapshots).
- Run a scratch copy of the **old descendant-loop reset** scoped to `labpool/p7_1_negative`, and prove B's snapshots are
  destroyed — reproducing the true P7 mechanism (not the plain parent-rollback, which would not destroy child snapshots
  and would be a scientifically false test).
- Destroy only `labpool/p7_1_negative` afterwards.
- Separately, prove the real guarded `bin/lab-reset` refuses a shared-parent (`labpool/victim`) request. These two facts
  together establish the guard is load-bearing.
