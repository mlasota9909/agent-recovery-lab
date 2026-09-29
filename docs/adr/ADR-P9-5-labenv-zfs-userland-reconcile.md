# ADR-P9-5 — Reconcile etc/lab.env ZFS_VERSION to the VM's actual zfsutils string

Status: accepted 2026-09-02 (P9 N008)
Authority: Article XX (resolve, record, continue), Article XVI (verification is
read-only w.r.t. the environment record), the P8 handoff (repro/manifest.json is
frozen at its producer_commit and not rewritten).

## Context

`etc/lab.env` recorded `ZFS_VERSION=2.4.1-1ubuntu5`. Between the P8 close
(2026-08-28) and P9's terminal gate, the victim VM `thesisvm01` received an OS
point update: `zfsutils-linux` advanced to `2.4.1-1ubuntu5.1`. The loaded ZFS
kernel module version (`ZFS_KMOD_VERSION`) is unchanged at `2.4.1-1ubuntu5`, so no
on-disk format, snapshot, or clone behaviour changed — only the userland package
version string.

`bin/lab-discover` reads the VM's `dpkg-query -W zfsutils-linux` and is the
authority on environment truth. The P0 regression gate's AC-18 idempotence sweep
runs `lab-discover` and requires `changed:false`. Against the stale value it
reports `changed:true`, failing P0 AC-18 and cascading into P1.1. Keeping the stale
value makes `lab-discover` permanently non-idempotent — P0 AC-18 can never pass.

## Decision

1. `etc/lab.env` is updated to `ZFS_VERSION=2.4.1-1ubuntu5.1` (one-line change,
   comments intact). This is environmental truth, not an experiment parameter.
2. `repro/manifest.json` is a **P8** deliverable, frozen at `producer_commit`
   `6a07c0c`; per the P8 handoff it is not rewritten. Its
   `environment.lab_env_sha256` (`cb774481…`) and `versions.zfs`
   (`2.4.1-1ubuntu5`) remain P8's historical record.
3. P9's environment fingerprint — `etc/lab.env` sha `d702508b…`, zfsutils
   `2.4.1-1ubuntu5.1`, ZFS kmod `2.4.1-1ubuntu5` — is recorded in the P9 close-out
   memo and `docs/P9-architecture-handoff.md`.
4. `lab_verify_p9.regression()` snapshots and restores `etc/lab.env` around the
   regression run so `lab-discover`'s comment-stripping rewrite never leaves the
   tree dirty (Article XVI); `regression.lab_env_drift_reverted` reports any
   residual formatting drift.

## Consequences

- No frozen contract changes; `frozen_contract_rows()` does not include `lab.env`.
- The P0/P1.1 regression returns to 5/5 once `lab.env` matches the VM.
- The P8 reproducibility manifest still validates (its checker verifies key
  presence, not value currency) and continues to describe P8's world.
- Reproducers on a machine whose VM still has `2.4.1-1ubuntu5` should expect
  `lab-discover` to normalise `lab.env` to their local string; the experiment is
  unaffected because the kmod version governs behaviour.
