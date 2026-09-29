# WI-P12-B — Provisioning (VM and lab substrate), scripted from an empty host

Goal: a clone of this repository plus a libvirt/KVM host can build the lab from nothing. Read the P12 spec (FR-2), the
P0 specification (`sdd/specs/P0-lab-substrate/spec.md`, `plan.md`, `tasks.md`) and the existing `bin/` scripts that
implement the P0 tasks. Depends on WI-P12-A (configuration in `etc/lab.env` + `etc/lab.local.env`).

## Reference environment (the development lab, to reproduce)
- Host: Ubuntu 26.04, libvirt 11 / virt-install 5.1, `qemu:///system`, network `default` (NAT, virbr0), the host user
  has passwordless sudo and is in the `libvirt` group. Host tools used by the lab: `pg_recvlogical` 18, `duckdb` CLI,
  `python3`, `ssh`.
- Guest: Ubuntu 26.04 cloud image, 8 vCPUs, 16 GiB RAM, one system disk, two data disks presented as `/dev/vdb` and
  `/dev/vdc` forming one striped `labpool` (lz4, recordsize 128K) with `labpool/victim/{pgdata,protected}` and
  `labpool/sandbox`; packages `zfsutils-linux`, `postgresql-18`, `postgresql-18-wal2json`, `python3`; the host user
  exists in the guest with the host's SSH key and passwordless sudo; the lab identities `lab_app` and `lab_agent`.

## P0 task to script mapping (verified)
T001 `bin/lab-discover`; T002 `bin/lab-zfs-init`; T003 `bin/lab-pgdata-relocate`; T004 `bin/lab-schema-init`;
T005 `bin/lab-incident`; T006 `bin/lab-wal-config`; T007 `bin/lab-slot`; T008 `bin/lab-identities`;
T009 `bin/lab-isolation-test`; T010 `bin/lab-heartbeat`; T011 `bin/lab-snapshot`, `bin/lab-snapshots`,
`bin/lab-coordinate` (loop: `bin/lab-snapshot-loop`); T012 `bin/lab-reset`; T015 `bin/lab-verify`. Related:
`bin/lab-ready` (read-only readiness gate), `bin/lab-consumer` (host-side consumer; unit from
`bin/lab-consumer-unit`), `bin/lab-barrier`, `bin/lab-incident-dataset` (isolated incident storage and cluster).
Steps that were manual in the original lab and need new scripts: VM creation; guest base packages; installing the
WAL receiver key line from `bin/lab-wal-receiver-key`; trusting the new guest's SSH host key.

## Do
Create `provision/` with:
1. `00-host-check.sh`: verify host prerequisites (commands and versions above, libvirt access, sudo, free space,
   `etc/lab.local.env` present); print exactly what is missing; `--install` installs missing apt packages.
2. `10-create-vm.sh`: download the Ubuntu 26.04 server cloud image (amd64) and verify it against the published
   SHA256SUMS; create the system disk (qcow2, 40 GiB) and two data disks (50 GiB each) in a libvirt storage pool
   named in `etc/lab.local.env`; write cloud-init user-data (hostname = VM name; the host user with the host's public
   key; passwordless sudo; packages above; `ssh_pwauth: false`); `virt-install --import --cloud-init user-data=...`
   with the resources above, `--network network=default`, no console; wait for cloud-init to finish and SSH to answer;
   write the VM address and SSH target into `etc/lab.local.env`. Refuse if a domain with the name exists unless
   `--recreate` (which destroys only that domain and its disks). Never touch any other domain.
3. `20-configure-guest.sh`: run the P0 steps in order using the existing scripts (discover and write `etc/lab.env`
   site keys to `etc/lab.local.env`; create `labpool` and datasets; relocate the PostgreSQL data directory to
   `DS_PGDATA`; schema, replica identity and DDL audit; identities; WAL settings; slot; heartbeat; snapshot and reset
   tooling). Map each P0 task to its script by reading the P0 tasks file and `bin/`; if a P0 step was done by hand in
   the original lab (no script exists), implement it as a small idempotent script under `provision/steps/`.
4. `30-configure-host.sh`: create the host evidence, archive and results roots; install the WAL receiver key line
   printed by `bin/lab-wal-receiver-key` into the host user's `authorized_keys` (idempotent, one line per checkout);
   configure host-side logical decoding access as the P0 scripts expect.
5. `40-healthcheck.sh`: run the P0 acceptance suite that applies to a fresh lab (`bin/lab-verify` or the P0 subset)
   and `bin/lab-ready`; write a JSON summary under `logs/provision/`; exit non-zero on any failure.
6. `all.sh`: 00 to 40 in order, stopping at the first failure, with a log under `logs/provision/`.
7. `99-destroy-vm.sh --yes`: remove only the replica domain and its disks named in `etc/lab.local.env`.
Every script: `set -euo pipefail`, repository root derived from its own location, idempotent where possible,
`--dry-run` prints the commands without running them.

## Do not
- Do not run any of these scripts, and do not contact the network, libvirt, a VM or PostgreSQL (they will be run and
  debugged separately). Syntax-check with `bash -n` and `shellcheck` if available.
- Do not modify experimental logic or frozen contracts. Do not create commits. Do not modify files outside this
  repository. Do not mention tools, assistants or the origin of the changes in any file, comment or message.

## Report
The P0-task-to-script mapping, every step you had to add because the original was manual, the new
`etc/lab.local.env` keys, and anything you could not determine from the repository.
