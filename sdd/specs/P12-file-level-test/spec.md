# P12 — Specification: File-Level Recovery Test and a Re-runnable Lab

## Problem

File-level recovery was designed into the lab but never connected end to end. Verified on the development lab:

| Stage | Defect |
|---|---|
| Capture | The incident generators call `lab-fs-capture <incident>` without its `diff`/`hash` subcommand. The tool exits with a usage error (3); the generators write empty `fs_diff.tsv` and `fs_hashes.tsv` placeholders and continue. |
| Snapshot records | Loop snapshots are recorded in the evidence folder, then replaced by the three snapshots the generator takes itself. Loop names have one-second resolution with an unlocked check-then-create, so collisions stop the loop; one loop ran unattended for 18 hours. |
| Reconciliation | Rule C-7 checks only workload operations whose action starts with `FS` (none are recorded) and matches by path substring; the file-damage workload records no paths. It therefore passes as "vacuous". |
| Analysis and inputs | File differences never reach the anomaly score, the ranker or any of the three model inputs. |
| Reference and checks | The file-damage reference leaves its file fields unimplemented; the checker parses two-column fingerprints while the capture tool writes three (snapshot, path, hash); missing damaged files are classed as legitimate loss; the verdict ignores file mismatches. |
| Portability | Paths are absolute to one checkout; the VM was created by hand; the WAL receiver is bound to one checkout path. |

The database-level test (mass deletion, SC-01) is unaffected in its reported results: its damage is database-only and
its verdicts rest on the row and column checks.

## Objective

1. Make file-level testing real, as a separate test with its own evidence, inputs, reference and checks.
2. Run it once, pre-registered, with the same comparison design as the database-level Primary Sweep.
3. Make the whole experiment re-runnable from a fresh clone, including creation of the VM, by scripts; the P12 run
   itself is executed through those scripts, which makes them the health check.

## Functional requirements

- FR-1 Portability. No absolute checkout paths. `etc/lab.env` is a committed template; `etc/lab.local.env` (ignored)
  holds site values (VM name and address, SSH alias, devices, ports, gateway). Every script derives the repository root
  from its own location.
- FR-2 Provisioning. Scripts create the VM from a published Ubuntu 26.04 cloud image (cloud-init user with the host's
  SSH key and passwordless sudo; one system disk; two data disks for `labpool`; libvirt default network), then run the
  guest and host configuration steps in the P0 order (pool and datasets, PostgreSQL on `DS_PGDATA`, schema and DDL
  audit, host evidence and archive roots, WAL settings and archive receiver key, slot, identities, heartbeat,
  snapshots, reset) and end with the P0 acceptance suite as the health check.
- FR-3 File capture. Each incident takes recorded snapshots every 2 seconds from before the baseline until after the
  damage window (collision-free names; one writer; every snapshot recorded on the host). For every consecutive pair the
  generator runs `lab-fs-capture diff`; for every recorded snapshot it runs `lab-fs-capture hash`. Any failure stops the
  incident. No placeholder files.
- FR-4 File operation records. The legitimate file workload and the injection record every intended file operation
  with its path and time. Rule C-7 becomes exact: every recorded file operation must appear in the captured
  differences of the interval that contains it, subject to the visibility rule in plan.md (ADR-3); a file scenario with
  zero matched operations fails.
- FR-5 File-level inputs. From the captured differences the lab builds the three input constructions for intervals
  (plan.md ADR-4 to ADR-6), with the same roles as for the database-level test and no actor names.
- FR-6 Answer reading. A file-level variant of the revised answer-reading rules resolves `interval=`, `snapshot=` and
  `ts=` locators from visible evidence to one recorded snapshot (ADR-7).
- FR-7 Reference and checks. The reference is the latest recorded snapshot before the damage starts. The checker
  compares restored files with the reference fingerprints, using a machine-readable damage manifest; retained file
  damage is checked damage; lost legitimate file work is loss. The checker reads the capture tool's three-column format.
  Verdict v2 counts file damage (ADR-8, ADR-9).
- FR-8 Comparators. A file-level fixed-rule ranker and the time estimate choose snapshots from the same evidence
  (ADR-10).
- FR-9 Study run. Three models (the Primary Sweep set and settings) × three inputs × five repeats = 45 calls, plus the
  ranker and the time estimate; every accepted point is restored and checked. Design and analysis plan are frozen
  (hashes) before the first model call.
- FR-10 Run-through. `run/all.sh` goes from an empty host (with libvirt and the model gateway available) to the
  final tables: provision, health check, incident, incident gate, inputs, study, restores, analysis, tables. Each stage
  can also be run alone and is idempotent or refuses to overwrite.

## Non-goals

- Re-running the database-level studies (Primary Sweep, Scaling Study, Rule-Repair Phase). Their records remain in the
  development repository. A replication of the mass-deletion incident through the same run-through is optional.
- Changing the model servers or the gateway. They are prerequisites checked by the preflight, not provisioned.
- Selective repair of individual files; recovery is to a recorded snapshot.

## Acceptance criteria (tier M unless noted)

1. `grep` finds no absolute checkout path in tracked files; a second clone at another path passes the unit tests.
2. Provisioning on an empty host creates the VM and passes the P0 acceptance suite (health check).
3. A dry-run file incident produces non-empty differences for every consecutive snapshot pair that had changes,
   fingerprints for every recorded snapshot, and a non-vacuous exact C-7.
4. The fresh file-damage incident's captured differences contain every damage target (the twelve deleted files, their
   directory and the overwritten file) and every legitimate file operation the visibility rule requires.
5. All three inputs contain the file changes of their intervals; the model-view guard passes; no actor names.
6. Controls on the fresh incident: reference = correct; first post-damage snapshot = checked damage remains;
   earliest snapshot = extra loss; a tampered restored file is detected.
7. The checker parses the real capture format (unit test on a captured file) and verdict v2 counts file damage.
8. Design, prompts, answer-reading rules and analysis plan are frozen with hashes before the first model call;
   model identities are recorded.
9. Every planned unit is accounted for; every accepted point is restored and checked.
10. `run/all.sh` completed the P12 run on this host (log retained).
11. (tier A) The author reviews the incident evidence and controls before the model run.
