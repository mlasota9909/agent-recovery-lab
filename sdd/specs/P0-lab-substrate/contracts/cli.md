# Contract — CLI surface

**Status:** FROZEN 2026-08-17 at end of P0. Article IV: every capability is a CLI, text in, JSON out, non-zero on failure.
Human-readable logging goes to stderr so stdout stays machine-parseable.

All CLIs live in `/home/mlasota/thesis/bin/` and source `etc/lab.env`.

| CLI | Task | Purpose | stdout |
| --- | --- | --- | --- |
| `lab-discover` | T001 | Probe host and guest; write/refresh `lab.env` | JSON of every discovered fact |
| `lab-snapshot` | T011 | Recursive snapshot of `DS_PARENT`; record LSN; force WAL switch | JSON snapshot record |
| `lab-snapshots` | T011 | List snapshots with recorded LSN | JSON array |
| `lab-coordinate` | T011 | Resolve a coordinate triple from `--lsn`, `--time` or `--snapshot` | coordinate JSON per `contracts/coordinate.md` |
| `lab-heartbeat` | T010 | Start/stop/status the 1 Hz heartbeat writer | JSON status |
| `lab-incident` | T005 | Allocate an incident id; repoint `archive/current`; create evidence dir | JSON incident record |
| `lab-slot` | T007 | Create/drop/status the logical slot; report lag | JSON slot state |
| `lab-reset` | T012 | `--tier t0\|t1\|t2`; roll victim back; leave evidence intact | JSON with tier, target, elapsed |
| `lab-isolation-test` | T009 | Assert FR-4.4 from each victim principal; supports `--regression` | JSON per-assertion results |
| `lab-verify` | T013 | Run the full P0 acceptance suite | JSON AC-1..AC-18 with PASS/FAIL |

## Conventions

1. `--json` is the default and only output mode on stdout. No decoration, no progress bars on stdout.
2. Exit `0` success, `1` assertion/verification failure, `2` missing precondition, `3` usage error.
3. Every CLI is idempotent and reports pre-existing correct state as success with `"changed": false`.
4. No CLI prints key material. Fingerprints and paths only.
5. No CLI reads provenance fields for any purpose other than scoring (Article II). `lab-coordinate` and any
   analytics CLI MUST NOT consult them.
