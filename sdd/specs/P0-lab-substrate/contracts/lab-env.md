# Contract — `etc/lab.env`

**Status:** FROZEN 2026-08-17 at end of P0. Keys may be ADDED by later tranches; existing keys may not be renamed or
re-purposed. Flat `KEY=value`, one per line, no interpolation, no sections, shell-sourceable.

Every script sources this file. No script may hardcode any value that appears here. T015 greps for violations.

## Keys written by P0

| Key | Written by | Example | Meaning |
| --- | --- | --- | --- |
| `LAB_HOST` | T001 | `r740core` | Host name |
| `LAB_ROOT` | T001 | `/home/mlasota/thesis` | Deploy root on host |
| `VM_NAME` | T001 | `thesisvm01` | libvirt domain name |
| `VM_SSH` | T001 | `thesisvm01` | SSH target (host alias or user@ip) |
| `VM_ADDR` | T001 | `203.0.113.40` | Discovered guest address |
| `DEV_A` | T001 | `/dev/vdb` | First ZFS device (guest-side) |
| `DEV_B` | T001 | `/dev/vdc` | Second ZFS device (guest-side) |
| `DEV_LOCATION` | T001 | `guest` | Verified attachment; `host` stops the build |
| `ZFS_VERSION` | T001 | `2.2.2` | Guest ZFS version |
| `PG_VERSION` | T001 | `16` | PostgreSQL major version |
| `PG_DATA` | T001 | `/var/lib/postgresql/16/main` | Data directory |
| `PG_PORT` | T001 | `5432` | Port |
| `ZPOOL` | T002 | `labpool` | Pool name |
| `DS_PARENT` | T002 | `labpool/victim` | Recursive snapshot target |
| `DS_PGDATA` | T002 | `labpool/victim/pgdata` | Dataset for the data directory |
| `DS_PROTECTED` | T002 | `labpool/victim/protected` | Dataset for the protected subtree |
| `MNT_PROTECTED` | T002 | `/srv/protected` | Protected subtree mount point in guest |
| `EVIDENCE_ROOT` | T005 | `${LAB_ROOT}/evidence` | Host evidence root |
| `ARCHIVE_ROOT` | T005 | `${LAB_ROOT}/archive` | Host WAL archive sink |
| `ARCHIVE_CURRENT` | T005 | `${LAB_ROOT}/archive/current` | Host-managed per-incident symlink |
| `BASEBACKUP_ROOT` | T005 | `${LAB_ROOT}/basebackup` | Host base backup root |
| `RESULTS_ROOT` | T005 | `${LAB_ROOT}/results` | Host results store |
| `ARCHIVE_MOUNT_IN_VM` | T005 | `/var/lib/postgresql/archive_sink` | Guest-side mount of the one append path |
| `SLOT_NAME` | T006 | `lab_slot` | Logical replication slot |
| `SLOT_PLUGIN` | T006 | `wal2json` | Output plugin |
| `SLOT_MAX_WAL_KEEP` | T007 | `8GB` | Bounded retention |
| `SLOT_WARN_RETAINED` | T007 | `64MB` | Pre-run logical-slot lag warning threshold |
| `SLOT_MIN_FREE` | T007 | `20GB` | Guest pgdata-pool free-space floor |
| `DB_NAME` | T004 | `labdb` | Scenario database |
| `ROLE_APP` | T008 | `lab_app` | Legitimate work role |
| `ROLE_AGENT` | T008 | `lab_agent` | Injector role |
| `OS_USER_APP` | T008 | `lab_app` | Legitimate OS user |
| `OS_USER_AGENT` | T008 | `lab_agent` | Injector OS user |
| `HEARTBEAT_TABLE` | T010 | `lab_heartbeat` | LSN/time index table |
| `HEARTBEAT_HZ` | T010 | `1` | Rows per second |
| `DDL_AUDIT_TABLE` | T004 | `lab_ddl_audit` | DDL trail inside the decoded stream |
| `SNAP_PREFIX` | T011 | `s_` | Snapshot name prefix |
| `SNAP_PRE_INJECTION` | T011 | `pre_injection` | T1 reset target |
| `SNAP_POST_CAPTURE` | T011 | `post_capture` | T2 reset target |
| `SNAP_PRISTINE` | T011 | `pristine` | T0 reset target |

## Rules

1. Values are discovered, never guessed. A missing value is a hard stop, not a default.
2. `DEV_LOCATION=host` contradicts the plan and MUST stop the tranche pending amendment.
3. Later tranches append keys with their own prefix; they do not edit P0's keys.
