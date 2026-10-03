# Agent recovery lab

This lab tests how a recovery point is chosen and checked after scripted damage to stored state while legitimate
work continues. One script, run as `lab_agent`, causes one kind of damage per scenario, and each scenario is run
as one study:

| Study | Damage | Entry point | Design and analysis plan | Records |
| --- | --- | --- | --- | --- |
| SC-01, deletion | One transaction deletes 200 rows | `run/optional/sc01-replication.sh` | [sc01-analysis-plan.md](run/optional/sc01-analysis-plan.md) | `records/SC01-replication/` |
| SC-02, files | Twelve files and their directory deleted, one retained file overwritten | `run/all.sh` | [P12](sdd/specs/P12-file-level-test/spec.md), [plan](sdd/specs/P12-file-level-test/plan.md), [contracts](sdd/specs/P12-file-level-test/contracts/fl-analysis-plan.md) | `records/P12/` |
| SC-03, schema changes | Three schema changes to one table | `run/optional/sc03-study.sh` | [P13](sdd/specs/P13-schema-and-update-studies/spec.md), [sc03-sc04-analysis-plan.md](run/optional/sc03-sc04-analysis-plan.md) | `records/SC03-study/` |
| SC-04, scattered updates | Twelve rows given damaging values, one update at a time | `run/optional/sc04-study.sh` | [P13](sdd/specs/P13-schema-and-update-studies/spec.md), [sc03-sc04-analysis-plan.md](run/optional/sc03-sc04-analysis-plan.md) | `records/SC04-study/` |

Every study runs the same stages: provisioning (00), preflight (10), incident (20), gate with control restores
(30), freeze (40), 45 model calls (50), comparators (60) and analysis (70). The captured evidence supports three
input constructions: raw excerpts (R0), structured summaries (R1) and written summaries (R2). Three models
receive each input five times. Accepted answers, a fixed-rule ranker and a time estimate are restored in
isolation and checked against a script-derived reference. Checked damage and lost legitimate work are reported
separately. The baseline uses known damage onset; each study is a single-incident feasibility experiment, not a
population study. `python3 records/<study>/verify.py` checks a kept study against its freeze. The database
studies' entry points are under `run/optional/` because their frozen analysis plans are pinned there.

## Prerequisites and configuration

Use a separate checkout and VM for a replication. The reference host runs Ubuntu
26.04, libvirt 11 and virt-install 5.1 with KVM, an active NAT network with DHCP,
an active host SSH service, passwordless sudo and membership in `libvirt`.
Provisioning allocates 8 vCPUs, 16 GiB RAM and 40+50+50 GiB guest disks. Allow
150 GiB on the storage-pool filesystem and 8 GiB in the checkout for preparation.
Host dependencies include Python 3, PostgreSQL 18 clients, DuckDB, OpenSSH,
libvirt clients, virt-install, qemu-img, cloud-init image support, curl, rsync,
iproute2 and standard GNU utilities. `provision/00-host-check.sh --install` can
install missing packages from configured apt repositories; `run/all.sh` expects
these prerequisites to be installed. See [provisioning](provision/README.md).

The model gateway and all three served models must already exist. Provisioning
does not change them. Inference uses only the gateway; the three backend URLs
are used to read served identity (id, root and maximum length). Their recorded
aliases are part of the experiment. The gateway credential is private and must
not be committed. The reference guest software is Ubuntu 26.04, PostgreSQL 18.6,
wal2json 2.6 and ZFS 2.4.1. Builds exposing `output_plugin_libraries` must list
wal2json; `lab-wal-config` handles this.

```bash
cp etc/lab.local.env.example etc/lab.local.env
# Edit the site file using the table below; keep secrets out of version control.
bin/lab-p9-modelset --build --served-identities
run/experiment.sh        # all four studies, one after another, on one VM
```

`run/experiment.sh` runs `run/all.sh` (the file study, which provisions the VM on a first run) and then the three
database studies in the same checkout and on the same VM. It stops at the first failure. After retiring a refused
attempt with `run/retire-attempt.sh`, resume with `run/experiment.sh --from sc01`, `--from sc03` or `--from sc04`.

Uncomment and set the site keys, including values that match template defaults.
Preflight requires explicit values for the VM, SSH account, network, storage,
devices, ports, gateway, credential-variable name, private address allowlist,
backends and served names. Provisioning writes the discovered VM address, SSH
alias and host route into the same file before preflight. Bash expansion is
supported; use `"$LAB_ROOT/..."` for checkout paths and `"$HOME/..."` for a host
key. Do not set `LAB_ROOT` to a different checkout. No site value belongs in an
executable script. `run/10-preflight.sh` prints resolved configuration, with
credential values redacted, before checking services.

`runtime/p9-model-set.template.json` is the empty identity template. The
registration command above writes the untracked `runtime/p9-model-set.json`
from observed identities, so the working tree stays clean; it refuses an
existing recorded registry or a P12 freeze. Registration
uses `/models`, not inference or tokenizer requests. `tokenizer_id` in this mode
identifies the served root; it is not a measured tokenizer fingerprint. Preflight
then compares all three actual digests with the recorded values and makes one
containment smoke call per model. These setup calls are separate from the 45
study observations. Identity drift fails preflight; it never repins a model.

All site values are listed in this table. Reference values were supplied as
verified on 2026-09-29. Generated values describe that build, not a fixed address
or a value to copy blindly. Experimental constants such as repeat count and
decoding are fixed by the contracts rather than configured per host.

| Key | Meaning | Reference environment | How to find/set in a new environment |
| --- | --- | --- | --- |
| `HOST_OS` | Discovered host OS; host was r740core | Ubuntu 26.04 | Provisioning reads `/etc/os-release` |
| `HOST_KERNEL` | Discovered host kernel | Recorded at discovery | `uname -r`; discovery records it |
| `VM_NAME` | Libvirt domain and guest hostname | `reclab01` | Choose an unused name; inspect `virsh list --all` |
| `VM_ADDR` | Guest PostgreSQL address | DHCP; `192.168.122.23` in verified build, earlier `192.168.122.3` | Provisioning writes its DHCP lease; never assume the example IP |
| `VM_SSH` | SSH target/managed alias | `lab-provision-reclab01-<uuid prefix>` | Provisioning writes the pinned alias; otherwise use an existing trusted target |
| `PROVISION_USER` | Guest SSH account, matching invoking host account | `mlasota` | Set to `$(id -un)`; cloud-init installs that account |
| `PROVISION_SSH_KEY` | Host private SSH key, public half required | `~/.ssh/id_ed25519` | Choose an existing noninteractive key and matching `.pub` |
| `PROVISION_URI` | Libvirt connection URI | `qemu:///system` | Use the URI hosting the intended domains and pools |
| `PROVISION_NETWORK` | Active NAT network with DHCP | `default` | Inspect `virsh net-list` and network XML |
| `PROVISION_STORAGE_POOL` | Directory pool for the three replica disks | `reclab` | Choose/review with `virsh pool-list --all` |
| `PROVISION_STORAGE_PATH` | Directory for the named pool | `/var/lib/libvirt/images/reclab` | Inspect pool XML or choose a directory with sufficient space |
| `PROVISION_IMAGE_BASE` | Published cloud-image/checksum source | `https://cloud-images.ubuntu.com/releases/26.04/release` | Use a verified source of the pinned Ubuntu 26.04 image and SHA256SUMS |
| `PROVISION_WAIT_SECONDS` | DHCP, SSH and cloud-init deadline | `1800` | Increase for slower image/package setup if needed |
| `PROVISION_VM_UUID` | Recorded ownership identity | Generated UUID | Written by provisioning; do not edit |
| `PROVISION_SYSTEM_VOLUME` | Owned system volume | `reclab01-system.qcow2` | Written by provisioning |
| `PROVISION_DATA_A_VOLUME` | Owned first data volume | `reclab01-data-a.qcow2` | Written by provisioning |
| `PROVISION_DATA_B_VOLUME` | Owned second data volume | `reclab01-data-b.qcow2` | Written by provisioning |
| `DEV_SYSTEM` | Virtio system-disk target | `/dev/vda` | Match intended libvirt attachment and guest `lsblk` |
| `DEV_A` | First ZFS data-disk target | `/dev/vdb` | Match intended libvirt attachment and guest `lsblk` |
| `DEV_B` | Second ZFS data-disk target | `/dev/vdc` | Match intended libvirt attachment and guest `lsblk`; all three must differ |
| `DEV_LOCATION` | Data-disk attachment location | `guest` | The replica requires guest-attached devices |
| `LAB_HOST` | Host address reachable from guest for archival | `192.168.122.1` | Provisioning writes the host route source to the guest |
| `HOST_PG_CIDR` | Host source allowed by guest PostgreSQL | `192.168.122.1/32` | Provisioning records the host route as a /32 |
| `HOST_ARCHIVE_USER` | Host archive owner and receiver SSH account | `mlasota` | Set to invoking host account; provisioning verifies/records it |
| `CONSUMER_UNIT` | Host consumer systemd template name | `reclab-consumer` | Choose a name unique per checkout on a shared host |
| `PG_VERSION` | Guest PostgreSQL major version | `18` | Pinned prerequisite; inspect installed packages |
| `PG_PORT` | Main guest PostgreSQL port | `5432` | Inspect guest cluster configuration |
| `SANDBOX_PORT` | Restore PostgreSQL port | `55432` | Choose a free guest port; restores are serialized |
| `INCIDENT_PORT_BASE` | First isolated-cluster port | `56000` | Choose a free guest port range |
| `INCIDENT_PORT_COUNT` | Size of isolated port range | `4000` | Reserve a range ending at or below 65535 |
| `PG_DATA` | Main guest PostgreSQL data directory | `/var/lib/postgresql/18/main` | Match guest cluster configuration |
| `PG_BIN` | Guest PostgreSQL executable directory | `/usr/lib/postgresql/18/bin` | Inspect the installed PostgreSQL package |
| `DB_NAME` | Victim database | `labdb` | Choose the database initialized by the schema step |
| `DDL_AUDIT_TABLE` | DDL audit relation | `lab_ddl_audit` | Match schema/audit configuration |
| `HEARTBEAT_TABLE` | Heartbeat relation | `lab_heartbeat` | Match heartbeat/schema configuration |
| `SLOT_NAME` | Main logical decoding slot | `lab_slot` | Choose a dedicated slot; isolated incidents allocate their own |
| `SLOT_PLUGIN` | Logical decoder | `wal2json` | Confirm the installed PostgreSQL plugin |
| `ZPOOL` | Guest ZFS pool | `labpool` | Choose the pool created on the two data disks |
| `DS_PARENT` | Parent victim dataset | `labpool/victim` | Derive from `ZPOOL` |
| `DS_PGDATA` | Main PostgreSQL dataset | `labpool/victim/pgdata` | Derive from `DS_PARENT` |
| `DS_PROTECTED` | Protected file dataset | `labpool/victim/protected` | Derive from `DS_PARENT` |
| `MNT_PROTECTED` | Protected guest mount | `/srv/protected` | Choose/match the protected dataset mount |
| `SANDBOX_DATASET` | Restore dataset parent | `labpool/sandbox` | Derive from `ZPOOL`; provisioning creates it |
| `SANDBOX_MNT` | Restore mount parent | `/labpool/sandbox` | Match the sandbox dataset mount |
| `ARCHIVE_MOUNT_IN_VM` | Guest archive SSH-key directory | `/var/lib/postgresql/archive_sink` | Use a guest PostgreSQL-owned directory |
| `OS_USER_APP` | Legitimate-work OS account | `lab_app` | Match identities/schema setup |
| `OS_USER_AGENT` | Injection OS account | `lab_agent` | Match identities/schema setup |
| `ROLE_APP` | Legitimate-work database role | `lab_app` | Match identities/schema setup |
| `ROLE_AGENT` | Injection database role | `lab_agent` | Match identities/schema setup |
| `LAB_ROOT` | Checkout root | Derived from entry-point location | Omit the override; never copy an absolute checkout path |
| `EVIDENCE_ROOT` | Evidence store | `$LAB_ROOT/evidence` | Keep a distinct directory within this checkout |
| `ARCHIVE_ROOT` | WAL archive | `$LAB_ROOT/archive` | Keep a distinct directory within this checkout |
| `ARCHIVE_CURRENT` | Active archive symlink | `$ARCHIVE_ROOT/current` | Must match the archive receiver's configured location |
| `BASEBACKUP_ROOT` | Base-backup store | `$LAB_ROOT/basebackup` | Keep a distinct directory within this checkout |
| `RESULTS_ROOT` | Study result store | `$LAB_ROOT/results` | Keep a distinct directory within this checkout |
| `RESULTS_GLOB` | Legacy database results glob | `results/*.jsonl` | Match legacy result placement; P12 uses explicit filenames |
| `RESULTS_SCHEMA` | Legacy row-schema path | `$LAB_ROOT/etc/results-row.schema.json` | Keep the checkout's schema |
| `SC01_SCENARIO_CONFIG` | Database replication scenario settings | `$LAB_ROOT/etc/scenarios/sc01.env` | Keep the pinned scenario configuration |
| `DUCKDB_BIN` | DuckDB executable | `duckdb` | Locate the installed executable on PATH |
| `P9_ENDPOINT` | Inference gateway URL | `http://127.0.0.1:4001` | Read the gateway service configuration; reference uses local k3s |
| `MODEL_API_KEY_FILE` | Private gateway credential file | `$LAB_ROOT/var/model/litellm.key` | Obtain gateway credential and store privately; not tracked |
| `MODEL_API_KEY_VAR` | Name of optional credential environment variable | `MODEL_API_KEY` | Choose the exported variable name; its value is redacted |
| `MODEL_API_KEY` | Optional secret value if the above name is retained | Private; not listed | Export it locally, or use the credential file |
| `P9_BACKEND_M1` | DeepSeek identity endpoint | `http://192.168.1.237:8000/v1` | Read backend service URL; must expose `/models` |
| `P9_SERVED_M1` | DeepSeek served id | `deepseek-v4-flash-0731-exl3-k2` | Read that backend's `/models`; gateway alias is `gb10a-deepseek-v4-flash` |
| `P9_BACKEND_M2` | Gemma identity endpoint | `http://100.70.64.14:8090/v1` | Read backend service URL; must expose `/models` |
| `P9_SERVED_M2` | Gemma served id | `gemma4-26b-a4b-it-qat-q4` | Read that backend's `/models`; gateway alias is `gympc-gemma4-26b` |
| `P9_BACKEND_M3` | Qwen identity endpoint | `http://192.168.1.168:8010/v1` | Read backend service URL; must expose `/models` |
| `P9_SERVED_M3` | Qwen served id | `qwen38-27b-mtp-nvfp4` | Read that backend's `/models`; gateway alias is `alienware-qwen38-27b` |
| `P9_MODEL_SET_JSON` | Model registry location | `$LAB_ROOT/runtime/p9-model-set.json` | Run stages require this canonical path |
| `LAB_HOSTS` | Private host/DNS allowlist | `localhost,reclab01` plus any site gateway/backend DNS names | List only intended private hosts; direct IP URLs need no extra DNS names |
| `LAB_PRIVATE_CIDRS` | Private-network allowlist | `10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,100.64.0.0/10,fd00::/8,fe80::/10` | Match site routes; loopback is always private |
| `MODEL_ENDPOINT` | Legacy baseline gateway URL | Use the same configured gateway | Set explicitly if running legacy baseline commands |
| `MODEL_LITELLM_HOST` | Legacy gateway host/DNS pin | `127.0.0.1` for reference gateway | Match `MODEL_ENDPOINT` host |
| `MODEL_LITELLM_PORT` | Legacy gateway port pin | `4001` | Match `MODEL_ENDPOINT` port |
| `MODEL_RUNTIME_JSON` | Legacy model runtime record | `$LAB_ROOT/var/model/model-runtime.json` | Needed only for historical baseline mode; P12 uses served identities |
| `ARM_B_PROMPT_TEMPLATE` | Database prompt wrapper | `$LAB_ROOT/etc/arm-b-prompt.txt` | Optional replication requires the canonical frozen wrapper |
| `TOKENIZER_PATH` | Offline tokenizer data | `$LAB_ROOT/vendor/tokenizer/lab-ws-punct-1.json` | Keep the committed tokenizer; no download required |
| `GUEST_OS` | Discovered guest OS | Ubuntu 26.04 | Recorded by discovery |
| `GUEST_KERNEL` | Discovered guest kernel | Recorded at discovery | Recorded by discovery |
| `ZFS_VERSION` | Discovered ZFS userland | 2.4.1 | Recorded by discovery |
| `ZFS_KMOD_VERSION` | Discovered ZFS kernel module | 2.4.1 | Recorded by discovery |
| `PG_SERVER_VERSION` | Discovered PostgreSQL version | 18.6 | Recorded by discovery |
| `WAL2JSON_VERSION` | Discovered decoder package version | 2.6 | Recorded by discovery |

## Run stages and outputs

Every entry point derives its root from its own path, uses `set -euo pipefail`,
serializes against other run stages and keeps a timestamped log in `logs/run/`.
`run/all.sh` runs 00 through 70, stops at the first failing stage and keeps one
top-level log containing the child-stage output. It runs the file study (SC-02);
the database studies have their own entry points (see below). Runtime/result files
are private to the checkout.

The times below are planning estimates, not measurements of this implementation.
Downloads, model latency, WAL volume and storage throughput dominate elapsed time.

| Stage | Inputs and command | Outputs | Approximate time |
| --- | --- | --- | --- |
| 00 | Site configuration; `provision/all.sh` | VM, configured lab, `var/provision/`, `logs/provision/`, health record under `logs/run/`; skips provisioning when existing health check passes | 15–60 minutes fresh; several minutes for health |
| 10 | Site file, recorded model set and running services | Redacted resolved values, three digest/containment checks and substrate health in `logs/run/preflight.json`; no main-cluster `lab-ready` requirement | 1–10 minutes normally; each smoke call allows 900 seconds |
| 20 | `run/20-incident.sh --scenario SC-02` | Printed incident id, fresh isolated cluster/slot and `evidence/SC-02/<incident>/`; attempt and id receipts in `logs/run/` | 2–10 minutes including setup; workload window is about 70 seconds |
| 30 | `run/30-incident-gate.sh <incident>` | Capture/C-7 checks, `fl-intervals.json`, `fl-inputs/{R0,R1,R2}/`, `fl-reference.json`, four controls/check reports and `logs/run/<incident>/gate.json` | 5–30 minutes; dominated by four restores |
| 40 | `run/40-freeze.sh <incident>`; successful current gate/preflight | `sdd/specs/P12-file-level-test/contracts/frozen-hashes.json`, exclusive creation; pins all five contracts, spec, plan, model set and three built views/content/prompts | Seconds |
| 50 | `run/50-study.sh <incident>`; verified freeze | 45 units in `results/fl-study-runs.jsonl`; call/reply/answer/check journals under `logs/run/<incident>/units/`; `fl-checks/` and `var/restore/` reports | Tens of minutes to hours; 45 × up to 900 seconds for inference plus restores |
| 60 | `run/60-comparators.sh <incident>`; frozen incident | `fl-rank.json`, `fl-naive.json`, checked coordinates in `results/fl-comparators.jsonl` and comparator journals | Seconds with cached checks; otherwise two restores |
| 70 | `run/70-analysis.sh`; frozen design and result files | `analysis-out/fl/`: cells, per-unit values, loss aggregates, comparators and exploratory tables as CSV/Markdown; `summary.json` with every count and completeness | Usually seconds; no live services |

Paths beginning `fl-` in the evidence column are below the named incident's
evidence directory. Result filenames use `RESULTS_ROOT` when configured.
The freeze pins the analysis plan; study and analysis recheck the frozen bytes.
Every study call records its start after the freeze. Nonacceptance has no restore
verdict. Failed checks retain null counts; unchecked accepted points remain
pending. Missing planned units are explicit. The final analysis returns failure
when units/comparators are missing, accepted checks are pending or cleanup failed.
Execution failures remain observations and are never silently replaced.

For the spec's manual evidence review, run stages 00–30 separately and inspect
`gate.json`, the three inputs and controls before running stages 40–70.

`run/dry-run.sh` rehearses stages 20 and 30 on the provisioned VM in a separate
log scope, `logs/dry-run/<UTC time>/`, after stage 10. A dry-run incident has
its own evidence folder and is never frozen, studied or compared: stages other
than 20 and 30 refuse a dry-run scope. `logs/run/` holds the one study incident.
The file-level study of record is kept in `records/P12/`; a clone runs its own
independent study, and its freeze stays untracked.

`run/all.sh` always uses `logs/run/` and does not rehearse. If a rehearsal
fails after allocating its incident, run `bin/lab-incident --close` (it closes
the incident named by `archive/current` and stops its consumer) before the next
rehearsal; stage 20 refuses to start while an incident is open.

If stage 20 or 30 refuses an incident in `logs/run` (for example because a capture
rule failed), `run/retire-attempt.sh "<reason>"` closes that incident and moves the
attempt's records to `logs/superseded/<UTC time>/` with the reason; then run the
stages (or `run/all.sh`) again. It refuses once a freeze exists.

## Resuming and independent execution

Stages 00 and 10 can be checked again; once the replica holds experiment
incidents, stage 00 skips provisioning and stage 10 checks the lab. The provisioning stage never automatically
replaces an existing domain. Follow `provision/README.md` for an interrupted build.
Stage 20 refuses an open incident and refuses a second generation attempt for the
same run. An unsuccessful attempt retains its receipt for investigation; it is
not automatically replaced. Stage 30 deterministically rebuilds derived inputs
before freezing and reuses checks only when their source/probe digests agree.
It refuses input rebuilding after a freeze. Stage 40 always refuses overwrite.

Resume a frozen study with `run/50-study.sh <incident>`, followed by stages 60
and 70. Stage 50 appends exactly one final record per unit and skips every
recorded unit, including failures. A durable start receipt precedes inference.
If interrupted after saving a reply, resumption reads that reply without another
call. If interrupted without a saved reply, it records an execution failure with
no replacement call. Finished per-unit journals close the gap between completion
and appending the result row. Interrupted checks without a saved report remain
explicitly pending; inspect the retained sandbox/check journal before any manual
reconciliation. Stage 60 has the same completed-record skip behavior, and snapshot
checks can be shared. Partial JSONL tails, duplicate units, foreign incidents,
changed frozen bytes and stale check reports cause refusal. Never delete failure
records to obtain replacement observations. A new independent study needs a fresh
checkout, VM/run scope and freeze.

Stage 70 can be repeated offline and replaces only its derived tables. It can
produce incomplete tables for an interrupted study, with explicit missing/pending
counts, but will not label them final. `summary.json` retains all descriptive
counts, explicit denominators, per-unit losses, sums/medians/ranges and exploratory
test block counts/exclusions. Comparators and controls are not pooled with models.

## Database studies (SC-01, SC-03, SC-04)

```bash
run/optional/sc01-replication.sh        # deletion study, stages 00 to 70
run/optional/sc03-study.sh              # schema-change study, stages 00 to 70
run/optional/sc04-study.sh              # scattered-update study, stages 00 to 70
# Or one stage at a time for a named incident, for example:
run/optional/sc03-study.sh --stage 20
run/optional/sc03-study.sh --incident SC-03_YYYYMMDDTHHMMSSZ --stage 30
run/optional/sc03-study.sh --incident SC-03_YYYYMMDDTHHMMSSZ --stage 40
run/optional/sc03-study.sh --incident SC-03_YYYYMMDDTHHMMSSZ --stage 50
run/optional/sc03-study.sh --incident SC-03_YYYYMMDDTHHMMSSZ --stage 60
run/optional/sc03-study.sh --incident SC-03_YYYYMMDDTHHMMSSZ --stage 70
# Rehearse stages 20 and 30 in a separate scope:
LAB_RUN_SCOPE=dry-run/$(date -u +%Y%m%dT%H%M%SZ) run/optional/sc03-study.sh --stage 20
```

Each entry point exposes `--stage 00|10|20|30|40|50|60|70|all`, with `all` the
default; stages 30 to 70 need `--incident`. A dry-run scope runs only stages 20
and 30. The three studies use the database inputs and prompt, the revised P11
visible-locator rules, the fixed 45-unit design and verdict v1 checks. They run
in the same checkout and on the same VM as the file study; `run/experiment.sh`
runs all four in order. SC-01 refuses the earlier headline incident
named in `lib/lab_repr.py`, which stays read-only.

SC-01 uses the existing SC-01 generator; its driver is `bin/lab-p9-sweep
--incident <incident> --revised-rules`, and the reference, earliest and
post-damage controls must pass before its exclusive freeze. SC-03 and SC-04 use
`bin/lab-generate-dbscen` (an isolated incident cluster with the SC-01
legitimate work, the scenario's own table and work, and the injection, every
operation recorded), `bin/lab-validate-dbscen` (damage counted in units) and
the driver `lib/lab_dbscen_study.py`. Their gate requires complete
reconciliation of every operation, injected ones included, ordered windows and
four controls before the freeze: the reference, a point inside the damage's first
open transaction, the earliest snapshot and the first snapshot after the damage. An
unfrozen attempt is retired with `run/retire-attempt.sh --sc01|--sc03|--sc04
"<reason>"`.

Output is separate per study: `logs/run/<incident>/sc0N/`,
`results/sc01-replication-<incident>.jsonl` or `results/sc0N-study-<incident>.jsonl`,
`results/sc0N-comparators-<incident>.jsonl` and `analysis-out/sc0N/<incident>/`.
The kept studies are `records/SC01-replication/`, `records/SC03-study/` and
`records/SC04-study/`.

## Teardown and verification limits

```bash
provision/99-destroy-vm.sh --yes
```

Teardown validates ownership and removes only the recorded VM and its three
volumes. It retains evidence, results, downloaded images, pool and host SSH/systemd
configuration; see `provision/README.md` for the exact scope.

Offline checks (`tests/`) cover run journals, interruption handling, frozen-byte
rejection, capture/C-7 gating, accounting, damage counting and statistics with
simulated responses, and run no lab commands. The live runs are the four studies
kept in `records/`, with the fresh-clone reproduction of the file study in
`records/P12/reproduction/`. The P0 health suite explicitly reports its omitted
historical review criteria; those are not fresh acceptance evidence.
