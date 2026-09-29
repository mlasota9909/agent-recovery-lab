# WI-P12-A — Portability

Goal: this repository must run from any clone location on any host with the prerequisites, with site-specific values
in one ignored file. Read `sdd/specs/P12-file-level-test/spec.md` (FR-1) and `plan.md` first.

## Do
1. Replace every absolute checkout path (for example `<repo>`, `<old-checkout>`) in tracked files
   with a path derived at run time from the repository root: shell scripts derive it from their own location
   (`$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)`), Python from `Path(__file__).resolve().parents[...]` or a single
   shared helper. Documentation examples use `<repo>`.
2. Split configuration: `etc/lab.env` becomes the committed template with neutral defaults and comments; site values
   (VM name, VM address, SSH alias, guest devices, ports, gateway URL and backend addresses, archive SSH user) move to
   `etc/lab.local.env`, which is git-ignored and loaded after the template by the existing env loader(s). Add
   `etc/lab.local.env.example` documenting every key. `LAB_ROOT`, `EVIDENCE_ROOT`, `ARCHIVE_ROOT` and similar default to
   folders under the repository root.
3. The WAL receiver: `bin/lab-wal-receive` must write into this checkout's archive root. Add `bin/lab-wal-receiver-key`
   that prints (does not install) the `authorized_keys` line with the forced command pointing at this checkout's
   receiver, for the provisioning step to install.
4. Output folders: any code writing under a `thesis/` folder writes under `analysis-out/` instead (keep file names).
   Record run outputs (`evidence/`, `archive/`, `results/`, `logs/`, `var/`, `runtime/`, `basebackup/`,
   `analysis-out/`) are git-ignored except a `.gitkeep`; keep `runtime/p9-model-set.json` tracked as a template.
5. Keep behaviour otherwise identical. Do not change any experimental logic, thresholds, contracts or frozen files
   under `sdd/specs/*/contracts/`.
6. Tests: existing unit tests under `tests/` must pass. Add a test that fails if a tracked file contains an absolute
   path under `/home/`.

## Do not
- Do not run any command that contacts the network, a VM, PostgreSQL, ZFS or libvirt.
- Do not create commits. Do not modify files outside this repository.
- Do not mention tools, assistants or the origin of the changes in any file, comment or message.

## Report
List the files changed, the loader behaviour, the new keys in `etc/lab.local.env.example`, the test results, and any
path you could not make relative (with the reason).
