# Runbook — restore P2 readiness from an invalidated or inactive replication slot

**Status:** tested in P1.1 X004 (`logs/review/X004/runbook-run.log`).  
**Gate:** P2 must not start until `bin/lab-ready` exits 0 (ADR-P1.1-4).

This procedure restores a usable logical-decoding slot by **rolling the victim
back to a ZFS snapshot that still contains the slot**. Allocating a replacement
replication slot after `wal_removed` would desynchronise it from the host-side
ledger and silently corrupt the evidence stream.

## Warning

Rollback **discards current victim state** (PostgreSQL data directory and the
protected dataset). That is acceptable at P1.1 close because the open incident
is a quarantined P1 stub-only null run (`results/fixtures/`). It is **not**
acceptable once real experimental incidents exist — freeze evaluation of those
incidents first.

## Choose the reset tier

Discover the open incident:

```bash
INC=$(basename "$(readlink -f "$ARCHIVE_CURRENT")")
```

Inspect `archive/$INC/snapshots.json` (or `bin/lab-snapshots`) for a snapshot
that is **not** `invalidated`:

- Prefer **t2** (`post_capture`) when that snapshot is still valid — it is the
  closest consistent capture point and still holds the slot.
- Use **t1** (`pre_injection`) only if you need pre-damage guest state and that
  snapshot is still valid.
- Do not use **t0** (`pristine`) unless a valid pristine snapshot exists; P1
  incidents typically have none.

If neither t1 nor t2 is valid, stop. Do not invent a slot.

## Procedure

Work from `<repo>` with `etc/lab.env` sourced. Substitute the
incident id discovered above; do not hard-code it.

1. **Stop PostgreSQL** (required; a live cluster makes `lab-reset` exit 2 with
   no rollback):

   ```bash
   ssh -o BatchMode=yes "$VM_SSH" "sudo -n systemctl stop postgresql@${PG_VERSION}-main"
   # wait until pgrep -x postgres fails
   ```

2. **Roll back** to the chosen snapshot that still contains the slot:

   ```bash
   bin/lab-reset --tier t2    # or t1; see above
   ```

   `lab-reset` restarts PostgreSQL itself.

3. **Start the consumer** for the open incident (do not pass `-d postgres`;
   `lab-consumer` already uses `DB_NAME` from `lab.env`):

   ```bash
   bin/lab-consumer start "$INC"
   ```

4. **Barrier** until `lab-slot --check` exits 0:

   ```bash
   bin/lab-barrier
   ```

5. **Heartbeat** must be running so the evidence stream has WAL to append
   (`lab-ready` requires `db.jsonl` to grow or `confirmed_flush_lsn` to
   advance). This is the existing 1 Hz writer, not a new slot:

   ```bash
   bin/lab-heartbeat --start
   ```

6. **Confirm**:

   ```bash
   bin/lab-ready
   ```

   Exit 0 with `ready: true`, `slot_active: true`, `invalidation_reason: null`,
   `slot_check: ok`, `db_jsonl_growing: true`. `slot_name` must equal the
   pre-recovery `SLOT_NAME` from `lab.env`.

## Do not

- Do not allocate a replacement replication slot, in `labdb` or in `postgres`.
- Do not treat `lab-ready` as a repair tool; it is read-only.
