# P0 acceptance memo

Date: 2026-08-17. Host `r740core`, guest `thesisvm01`. Deploy root `<repo>`.

## What P0 delivers

A contained PostgreSQL-on-ZFS lab: two-disk stripe `labpool`, datasets `pgdata` (8K) and
`protected`, identities `lab_app`/`lab_agent`, WAL archive over a forced SSH append
channel, logical decoding via `wal2json`, 1 Hz heartbeat, three-tier ZFS reset, and
coordinate resolution with skew in milliseconds and bytes. Contracts under
`sdd/specs/P0-lab-substrate/contracts/` are frozen.

## Five findings and closure

See `logs/review/R007/findings-closure.md`. F-1..F-5 are **CLOSED**.

| ID | In one line |
| --- | --- |
| F-1 | Receiver hatch deleted; command surface enumerated; regression mutates host keys |
| F-2 | Host `lab-consumer@` drains `lab_slot`; `--check` fails closed |
| F-3 | No prose matcher; 9 mechanical / 9 attested; AC-6 and AC-14 live |
| F-4 | `lab-reset` refuses while PostgreSQL is live; both children restore when stopped |
| F-5 | `.pre-zfs` gone; `docs/environment.md` generated from `lab.env` |

## Tier split

**TIER M: 9/9 PASS · TIER A: 9/9 PASS · TOTAL: 18/18**

Mechanical: AC-1, AC-6, AC-10, AC-12, AC-13, AC-14, AC-15, AC-16, AC-18.
Attested: AC-2, AC-3, AC-4, AC-5, AC-7, AC-8, AC-9, AC-11, AC-17.
Load-bearing AC-6 (before-images) and AC-14 (heartbeat index) are mechanical.

## Measured facts worth citing

| Quantity | Value | Source |
| --- | --- | --- |
| Steady-state retained WAL | **3360 bytes** (warning threshold 64 MiB) | `SLOT_STEADY_RETAINED_BYTES`; R003 |
| Full-cycle time | **49.335 s** | T015 `full_cycle_elapsed_ms=49335` |
| Cross-layer skew (explicit snapshot) | 0 ms, 0 bytes | T011 `snapshot_first` |
| Cross-layer skew (time-first, degraded gap) | 30858 ms, 16797344 bytes | T011 `final-gap.json` |
| Guest / host | Ubuntu 26.04 LTS, kernel 7.0.0-29-generic | `docs/environment.md` |
| PostgreSQL | 18.4 (Ubuntu 18.4-0ubuntu0.26.04.1) | `PG_SERVER_VERSION` |
| wal2json | 2.6-3 | `WAL2JSON_VERSION` |
| ZFS | 2.4.1-1ubuntu5 (kmod and userland) | `ZFS_KMOD_VERSION` / `ZFS_VERSION` |

## Sample-size implication of 49.335 s

An unattended 8-hour matrix has about 8×3600/49.335 ≈ **583** full
snapshot–inject–capture–reset cycles. That number replaces “maximum achievable
sample will be attempted” in the P1 stratified sample-size plan: pick strata
counts that fit inside 583 cycles (plus overhead for consumer catch-up and
operator gates), rather than treating sample size as unbounded.

## Standing limitations

1. Isolation is logical and same-host, not a physical air-gap or WORM store.
2. Filesystem recovery granularity is the snapshot interval.
3. T0 is ZFS rollback, not a libvirt snapshot.
4. P0 was accepted only after P0.1 remediation.
5. Acceptance is two-tiered; seven of the original live checks plus two upgrades
   are mechanical, nine are attested against machine-readable artefacts.
6. The evidence channel’s accepted command surface is the enumerated append class.

## P1 go

P0 is accepted after P0.1. The substrate is safe to leave running: the consumer
is supervised, slot lag fails closed, isolation is hatch-free and enumerated.
**P1 may begin.**
