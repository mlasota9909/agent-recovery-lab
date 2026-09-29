# Provisioning the replica

Copy `etc/lab.local.env.example` to `etc/lab.local.env` and set `VM_NAME`,
`PROVISION_STORAGE_POOL` and `PROVISION_SSH_KEY`. Run as the host account with
passwordless sudo and membership in `libvirt`. The SSH key's public half must
exist and the private half must work without an interactive prompt. Use a
separate checkout and domain for a replica.

```bash
provision/all.sh --dry-run
provision/all.sh --install
# Explicit replacement of this checkout's recorded replica:
provision/all.sh --recreate
# Explicit removal of this checkout's recorded replica:
provision/99-destroy-vm.sh --yes
```

Each stage also runs independently. Every shell entry point accepts `--dry-run`,
prints its commands and makes no external connections or writes. Python helpers
are called through those entry points. `all.sh` runs 00, 10, 20, 30 and 40,
stops at the first failure, and retains a log in `logs/provision/`. Provisioning
operations use a checkout lock. Stage 10 refuses an existing domain; it is
deliberately not a resume command. After an interrupted build, use `--recreate`
or continue with stage 20 if creation and cloud-init already succeeded.

00 checks Ubuntu 26.04, libvirt >=11, virt-install >=5.1, PostgreSQL clients 18,
DuckDB, Python, SSH, supporting commands, KVM/libvirt access, passwordless sudo,
the active default NAT network, storage capacity and the local configuration.
`--install` installs missing apt packages from already configured repositories.
It reports packages with no apt candidate, including DuckDB if unavailable; it
does not select an unrecorded download source. The host needs 150 GiB available
on the pool filesystem and 8 GiB in the checkout for image preparation. An
absent named directory pool is created by stage 10; an existing active directory
pool is reused. Other pool types are refused. The existing default NAT network
and host SSH service must be active.

10 downloads `ubuntu-26.04-server-cloudimg-amd64.img` and `SHA256SUMS` from
`https://cloud-images.ubuntu.com/releases/26.04/release/`, checks the exact image
entry and hash, and imports a standalone 40 GiB qcow2 system disk plus two
50 GiB qcow2 data disks. There is no shared image backing file. The guest has
8 vCPUs and 16 GiB RAM. Cloud-init installs the host account, its public key,
passwordless sudo and guest packages, with password SSH disabled. A generated
guest host key is included in the seed and pinned before the first SSH call;
there is no unauthenticated host-key scan. The SSH alias is installed as a
managed block in the host account's SSH config, with checkout-local known hosts.
DHCP and SSH waits are bounded, and cloud-init must finish successfully.

20 uses the existing P0 commands. Host roots and the WAL append channel are
shared steps also invoked here because T005 is a prerequisite of T006. Stage 30
repeats these checks idempotently and ensures the consumer and reset anchors
exist. The archive's active scope is allocated once the slot and host consumer
unit are ready. The host route source is recorded as `LAB_HOST` and
`HOST_PG_CIDR`; `lab-wal-config` grants decoding/replication access only to that
host's /32. The guest archive private key remains in the guest. Its public key
passes through `bin/lab-wal-receiver-key`, and exactly one marked forced-command
line per checkout is installed in the host user's `authorized_keys`. The guest
postgres account trusts the host's locally read SSH public host key.

The pool and protected dataset inherit 128K records with lz4 compression. The
existing T002 command explicitly uses **8K for PGDATA**; provisioning preserves
that P0 setting. `labpool/sandbox` is added by a small supplemental step.

The consumer runs as a host systemd template unit named by `CONSUMER_UNIT`
(default `lab-consumer`, installed as `<name>@.service`). A different existing
template with the same name is refused, so this setup never takes one over from
another checkout; give each checkout that shares a host its own `CONSUMER_UNIT`. A provisioning-only SC-01 scope is used because the
consumer accepts shared-substrate SC-01 IDs; later scenario IDs require their
own incident runtime. No scenario workload, injection, study or model call runs.
All three reset labels describe undamaged baseline state. Provisioning installs
the reset prerequisites without performing a rollback.

40 runs the fresh P0 subset and `bin/lab-ready`, writes a timestamped JSON
summary under `logs/provision/`, and fails on any failed check. It reuses the
live before-image and heartbeat checks from `bin/lab-verify.py`, plus discovery,
real WAL delivery, append/overwrite refusal, slot health, isolation and its
deliberate regression, snapshot anchors, LSN resolution and the setup idempotence
sweep. The JSON explicitly lists omitted historical review criteria. It does
not treat the development lab's attestations as results for this replica.

Re-running configuration requires that the provisioning scope is still active;
an experiment's archive pointer is never repointed by configuration. Recreation
stops this replica's provisioning consumer and clears only its active archive
pointer before removing the VM. A new scope is allocated for the new VM UUID.
Old evidence, archives and results remain intact. Teardown validates the domain
UUID, exact disk attachments, recorded pool/volume paths and other domains'
storage references before deleting the recorded domain and volumes individually.
It never uses a wildcard or `--remove-all-storage`. Pools, downloaded images,
SSH configuration, receiver authorization, and the host consumer template remain
available for rebuilding; teardown is not a host uninstall command.

## P0 task mapping

| Task | Existing implementation and provisioning use |
| --- | --- |
| T001 | `bin/lab-discover`, stage 20; writes discovered values to `etc/lab.local.env` |
| T002 | `bin/lab-zfs-init`, stage 20; `steps/sandbox.sh` adds the restore dataset |
| T003 | `bin/lab-pgdata-relocate`, stage 20 |
| T004 | `bin/lab-schema-init`, stage 20; schema, full replica identity and DDL audit |
| T005 | `bin/lab-incident`; `steps/host-roots.sh`, `steps/wal-channel.sh`, `steps/baseline.sh` |
| T006 | `bin/lab-wal-config`, stages 20/30; host /32 access, archiving and wal2json slot |
| T007 | `bin/lab-slot --create`, stages 20/30; live health in stage 40 |
| T008 | `bin/lab-identities`, stage 20 |
| T009 | `bin/lab-isolation-test`, stage 20 and stage 40; enumeration and regression in 40 |
| T010 | `bin/lab-heartbeat --start`, stage 20 |
| T011 | `bin/lab-snapshot`, `bin/lab-snapshots`, `bin/lab-coordinate`; baseline step and health check. `bin/lab-snapshot-loop` remains available for incidents |
| T012 | `bin/lab-reset`; baseline step prepares pristine/pre-injection/post-capture labels. Live rollback checks are not claimed |
| T013 | `bin/lab-zfs-diff-proof`, `bin/lab-zfs-diff-json`, `bin/lab-zfs-diff-review`; full filesystem review is deferred |
| T014 | Live before-image and heartbeat functions in `bin/lab-verify.py` reused in 40; full DDL/transaction-boundary review is deferred |
| T015 | `bin/lab-verify` is the historical full suite; `lib/healthcheck.py` runs the fresh subset with explicit omissions |

Related existing commands are `bin/lab-ready`, `bin/lab-consumer`,
`bin/lab-consumer-unit`, `bin/lab-barrier` and `bin/lab-incident-dataset`. The last
two belong to later capture/isolated-incident setup and are not run here.

## Previously manual setup now scripted

- Host prerequisite/package checks, directory-pool creation, verified cloud-image
  download, disk allocation, VM import, cloud-init and address discovery.
- Guest base-package completion, ZFS module loading, cluster startup and private
  administrator-home permissions (`steps/guest-base.sh`).
- Sandbox dataset creation (`steps/sandbox.sh`).
- Host roots and evidence policy file (`steps/host-roots.sh`).
- Guest-to-host archive key creation, forced receiver authorization, and host
  SSH-key pinning in the guest (`steps/wal-channel.sh`).
- New guest SSH trust and a checkout-specific SSH alias (stage 10).
- Rendering/installing the consumer unit (`steps/consumer-unit.sh`).
- Provisioning scope, consumer startup and reset-label initialization
  (`steps/baseline.sh`).

## Site keys and outstanding verification

New inputs are `PROVISION_STORAGE_POOL`, optional `PROVISION_STORAGE_PATH`,
`PROVISION_SSH_KEY` and `PROVISION_WAIT_SECONDS`. Generated ownership keys are
`PROVISION_VM_UUID`, `PROVISION_SYSTEM_VOLUME`, `PROVISION_DATA_A_VOLUME` and
`PROVISION_DATA_B_VOLUME`. All are documented in `etc/lab.local.env.example`.
Existing `VM_ADDR`, `VM_SSH`, `LAB_HOST`, `HOST_PG_CIDR` and `HOST_ARCHIVE_USER`
are populated automatically; P0 commands record their existing discovery keys.
The shared `etc/lab.env` template remains unchanged.

The repository cannot establish the target host's pool, key path, installed
versions, free space, DHCP address or configured apt candidates. The release
image URL, published checksum entry, package availability and cloud-init/libvirt
behavior require verification when provisioning is executed. The scripts refuse
missing or inconsistent prerequisites. No live execution is claimed here.
Fresh full-suite filesystem, DDL/provenance, timing, incident/reset and rollback
review artifacts are not present; stage 40 reports their omission rather than
importing historical proofs. The original 128K-pool/8K-PGDATA distinction is
preserved and needs review if the reference intended 128K specifically for
PGDATA as well.

Static validation: `bash -n` passed for all 14 shell files and the two embedded
Bash blocks; both Python modules parsed successfully. `shellcheck` was not
installed. Provisioning, dry runs, acceptance checks and network access were not
executed during this change.
