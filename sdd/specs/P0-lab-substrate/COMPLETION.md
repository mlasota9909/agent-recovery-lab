# P0 completion — 2026-08-17

P0 delivered the isolated evidence substrate, ZFS snapshot/reset primitives, PostgreSQL logical evidence path, identity isolation, coordinate resolver, and the full JSON acceptance verifier.

## Acceptance

`bin/lab-verify` exited 0 with AC-1 through AC-18 all PASS. The complete observed record is `logs/review/T015/verify-results.json`.

## Measured timings

- Throwaway recursive snapshot: 0.139 s.
- Throwaway rollback: 0.203 s.
- Rehearsal T1 rollback: 5.813 s; complete reset: 13.386 s.
- Rehearsal T2 rollback: 4.706 s; complete reset: 17.606 s.
- End-to-end mechanical cycle: 49.335 s.

The rehearsal inserted a legitimate `lab_app` change, applied `lab_agent` damage, resolved its coordinate, verified the damage absent after T1, recreated post-capture after T1 invalidation, and verified damage present after T2.

## Known limitations

Isolation is logical and same-host, not physical air-gap or WORM storage. Filesystem recovery is bounded by the snapshot interval. T0 uses ZFS rollback rather than a libvirt snapshot.

## Open items for P1

P1 adds the results-row contract and scenario semantics. Begin each capture with an active logical consumer: the final AC-10 status showed bounded retention but an inactive consumer and lag over the warning threshold.
