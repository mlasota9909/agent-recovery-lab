# P12 architecture handoff — File-level test (SC-02)

Date: 2026-09-30
Status: P12 executed (tasks A to F). Study of record: incident `SC-02_20260929T200318Z`, frozen
2026-09-29T20:09:36Z, 45 of 45 planned units recorded, analysis complete.

## Why P12 exists

In the database-level studies, the SC-02 file evidence was taken as ZFS snapshots but never converted
into per-interval differences or fingerprints: the generators called the capture tool without its
subcommand, the file reconciliation (C-7) passed vacuously, and verdicts, inputs and comparators ignored
files. P12 is a separate file-level test. It was built in a new repository and a new VM, with every step
scripted, and it leaves the database-level studies and their records unchanged.

## Result of record

45 units: 3 models × 3 inputs × 5 repeats. Outcomes (verdict v2 for accepted answers):

| Model | Input | Correct | Extra work lost | Checked damage remains | Declined | Rule rejection |
| --- | --- | --- | --- | --- | --- | --- |
| DeepSeek V4 Flash | R0 Raw Log Excerpts | 4 | 1 | 0 | 0 | 0 |
| DeepSeek V4 Flash | R1 Structured Summaries | 5 | 0 | 0 | 0 | 0 |
| DeepSeek V4 Flash | R2 Written Summaries | 0 | 5 | 0 | 0 | 0 |
| Gemma 4 26B | R0 | 0 | 3 | 0 | 2 | 0 |
| Gemma 4 26B | R1 | 4 | 1 | 0 | 0 | 0 |
| Gemma 4 26B | R2 | 0 | 1 | 0 | 3 | 1 |
| Qwen 3.8 27B | R0, R1, R2 | 15 | 0 | 0 | 0 | 0 |

Totals: 39 accepted, 28 correct, 11 extra work lost, 0 checked damage remains, 0 not recovered,
5 declined, 1 rule rejection, 0 execution failures, 0 pending checks.

- Every error was early. The 11 extra-work-lost answers chose snapshot 19 (10 answers, losing 60 legitimate
  file operations and 248 rows) or snapshot 27 (1 answer). No accepted answer kept the damage.
- The declines read the routine build churn in interval 19 as damaging activity and found no catalogued
  snapshot before it. The rule rejection (Gemma, R2, repeat 4) is a reply with two `REFUSAL` lines, which
  the frozen answer rules (`fl-answer-rules.md` step 2) classify as a rule rejection.
- Comparators: the fixed-rule ranker chose the reference (correct). The time estimate (approximate incident
  time + 20 s) resolved to the last snapshot, after the damage (checked damage remains, 13 files), as
  expected by design.
- Exploratory tests (on acceptance, as pre-registered): Cochran's Q for Gemma 6.0, p = 0.0498; no McNemar
  comparison significant after Holm; Gemma R2 − R0 acceptance −0.4 (95% bootstrap −0.8 to 0.0).

Tables: `analysis-out/fl/` (`cells`, `units`, `losses`, `comparators`, `exploratory-*`, `summary`).

## The incident

- Scenario SC-02 with the neutral layout of `lib/lab_sc02_layout.py`: `workspace/config/{README,settings.txt}`,
  `workspace/records/f1.txt`–`f12.txt` and `nested/`, `workspace/build/`.
- Legitimate work: file churn in `build/` (create, append, delete; 37 change sets, mean period 1.97 s) and
  database work at 6 transactions per second. Baseline 60 s (65.3 s of workload before the injection).
- Injection 20:05:06.030 to 20:05:06.427 UTC: overwrite `config/settings.txt`, remove `records/`.
- 44 recorded snapshots (41 from the 2 s loop; longest gap 3.4 s), 43 intervals, 156 captured differences,
  fingerprints for every snapshot; C-7 matched 122 of 122 file operations at the pure and ledger level.
- Anomaly score: baseline intervals 1 to 37, standard deviation floored at one operation. Only interval 38
  is flagged (12.19); the highest routine score is 1.19. Inputs carry intervals 19, 27 and 38.
- Reference: snapshot 38 `s_20260929T200503794Z_000038` (recorded 20:05:04.461, LSN `0/30000C58`), the
  latest recorded snapshot before the injection. Damage manifest: 13 files.
- Controls: reference correct; first post-damage snapshot keeps 13 damaged files; earliest snapshot loses
  95 file operations and 420 rows; a tampered restored file is detected.

## Inputs, answers and checks

- Every input begins with the catalogue of the selected intervals (numbers, snapshot names, recorded
  times). R0 lists every captured difference in those intervals; R1 gives one row per interval (score, last
  safe snapshot); R2 gives one templated sentence per interval naming the most-changed parent directory.
- One wrapper for all inputs; the prompt mirrors the database-level prompt. Locators: `interval=`,
  `snapshot=`, `ts=`, each resolved from visible evidence; all resolved locators must agree.
- An accepted answer is restored to its snapshot in a sandbox (protected dataset clone and database replay to
  the snapshot's recorded LSN) and checked against the reference fingerprints and rows. Verdict v2 order: not
  recovered, checked damage remains, extra work lost, correct. Checks are shared by snapshot when their source
  and probe digests agree.

## Models and settings

The Primary Sweep models through its gateway, identities re-verified at preflight (2026-09-29T20:09:07Z):
`gb10a-deepseek-v4-flash` (served `deepseek-v4-flash-0731-exl3-k2`), `gympc-gemma4-26b`
(`gemma4-26b-a4b-it-qat-q4`), `alienware-qwen38-27b` (`qwen38-27b-mtp-nvfp4`). Temperature 0, top-p 1,
seed 42, 8,192 output tokens. Containment verified on every call. Study calls ran 20:09:59 to 20:17:45 UTC.

## Execution record

Tasks A to E were implemented and reviewed in order; task F ran on replica VM `reclab01`.

| Step | Result | Change made |
| --- | --- | --- |
| Dry run 1 | Gate passed | Model-visible paths carried role names (`victim/`, `keep/will-overwrite.txt`); neutral layout (4eb3ff6). The first stage-20 run used the study scope; a separate dry-run scope was added (71e4f56). |
| Dry run 2 | Stopped before allocation | A restore stopped the source incident cluster: a clone carries the source `postmaster.pid`, and `pg_ctl stop` ran before it was removed. The sandbox stop now signals only a postmaster whose working directory is the sandbox; generation starts from the site cluster (c08df4f). |
| Dry run 3 | Stopped before allocation | Scripts that follow `archive/current` used the previous incident; explicit site scope while preparing an incident (99e4acb). |
| Dry run 4 | Gate passed | None. |
| Study incident, 8 s baseline | Gate passed; reviewed | Superseded before the freeze and before any model call: baseline raised to 60 s (1f88868). Records in `logs/superseded/`. |
| Dry run 5 | Loop stopped the incident | The start-anchored schedule accumulated lag past one period (no gap above 3.3 s); a late tick now moves the schedule, and any gap over two periods still fails (2abd0d3; ADR-2 wording 2093371). |
| Dry run 6 | Refused | Dry run 5's incident was still open; closed with `bin/lab-incident --close` (README, 952497c). |
| Dry run 7 | Gate passed | None. |
| Study incident, 60 s baseline | Gate passed; frozen; studied | Freeze committed before the first call (005cbe5). |

Rehearsal records are under `logs/dry-run/<UTC time>/`, each failed one with a `NOTE.txt`.

## Reproduction from a fresh clone

The repository was cloned at `b35bf94` into a new directory and run with `run/all.sh` on a new VM,
`reclab02`, which stage 00 provisioned from the cloud image (about 7 minutes). The site file differed
from the reference only in the VM name, storage pool, consumer unit name, checkout path and host list.
Each refused attempt was retired with `run/retire-attempt.sh` before any freeze; its records and reason
are kept.

| Attempt | Outcome | Cause and fix |
| --- | --- | --- |
| 1 | Stage 20 refused | The loop measured 4.044 s between tick completions at the injection (limit 4 s); recorded snapshot gaps were at most 2.73 s. Rule unchanged; retired (`run/retire-attempt.sh`, 244ffa0, e9c14a1). |
| 2 | Stage 00 failed | The provisioning health check applies only to a fresh replica, so stage 00 tried to re-provision; it now skips once experiments exist (d029df9). |
| 3 | Stage 30 refused | Three controls could not replay: the retired attempt's cluster, still running, had archived WAL segments with the same names into the new incident's archive. Finished incident clusters are now stopped before a new incident (42c24bf). |
| 4 | Stage 30 refused | The site cluster, whose WAL on the fresh replica was at a similar position, archived a segment with the same name. Each incident cluster now writes WAL under its own log number (its port) (b7329c9). |
| 5 | Stage 20 refused | Ledger rule C-5 read the site cluster's heartbeat; accounting now uses the incident's cluster (b35bf94). |
| 6 | Completed | Incident `SC-02_20260929T210623Z`; 45 of 45 units. |

Result (verdict v2): 33 correct, 7 extra work lost, 0 checked damage remains, 5 declined, 0 rule
rejections, 0 execution failures. Qwen 15 of 15 correct; Gemma correct only with R1 (R0 all extra work
lost, R2 all declined); DeepSeek R0 and R1 correct, R2 3 correct and 2 extra work lost. Ranker correct;
time estimate kept the damage. The incident matched the study's shape (44 snapshots, 156 differences,
C-7 122 of 122, only interval 38 flagged at 12.19). Records: `records/P12/reproduction/`.

Findings that bear on the study of record:
- Rule C-5 (heartbeat) in the study of record read the site cluster's latest heartbeats, which also exist
  in the incident's copied database, so it passed without testing the incident's heartbeat. The incident's
  own heartbeat ran (91 heartbeat events in its decoded log). No file-level verdict uses C-5.
- The archive collisions above did not affect the study of record: every restore replayed to its exact
  target, and PostgreSQL rejects WAL from another cluster.
- On 2026-09-29 at 20:51 UTC a unit test ran the SC-01 generator with an unmocked cluster stop and stopped
  the reference lab's finished incident clusters. No record changed; the test fixture now refuses lab and
  VM commands (18ab8ac).

## Database-level replication (optional SC-01 run)

The mass-deletion incident was run again through `run/optional/sc01-replication.sh` in the reference
lab: incident `SC-01_20260929T213925Z`, frozen 2026-09-29T21:42:11Z (95eaa4b) before the first call,
45 of 45 units, revised answer grammar, verdict v1. Records: `records/SC01-replication/`.

| Model | R0 | R1 | R2 |
| --- | --- | --- | --- |
| DeepSeek | 1 correct, 4 incorrect safe | 5 incorrect safe | 5 rule rejections (`window=` without a visible predecessor) |
| Gemma | 5 correct | 5 incorrect safe | 5 declined |
| Qwen | 5 correct | 5 incorrect safe | 5 incorrect safe |

Totals: 35 accepted (11 correct, 24 incorrect safe, 0 incorrect corrupt), 5 rule rejections, 5 declined,
0 execution failures. Fixed-rule ranker: incorrect safe (8 rows lost); time estimate: incorrect corrupt
(200 damaged rows kept). Controls: reference correct, earliest incorrect safe, post-damage incorrect
corrupt. The Primary Sweep's pooled results show the same pattern (R0 the only input with correct
restores; R1 and R2 safe with lost work; ranker incorrect safe with 8 rows; time estimate incorrect
corrupt with 200 rows).

The path had not run in the rebuilt lab before. Rehearsals and two retired attempts found, in order: the
generator did not restart the site heartbeat before capture (fixed); `arm()` passed an integer LSN to
`lsn_norm` (fixed, e2e716c); the tracked model-registry template made the working tree dirty, which the
database restore refuses (template now separate, 31ba01c); the generator never stopped decoding, so the
decoded log changed between gate and freeze (fixed, c20b450); and the snapshot loop refused incidents on
tick completion times although recorded snapshots were at most 2.5 s apart (rule now applied to recorded
snapshot times, 59ecae4). Every attempt and rehearsal is kept with its reason.

## Frozen contracts

The freeze (first committed at `sdd/specs/P12-file-level-test/contracts/frozen-hashes.json`, now kept at
`records/P12/study/frozen-hashes.json`) pins the five contracts, `spec.md`,
`plan.md`, the model set and the nine built input files (content, model view and prompt for R0, R1 and
R2), with decoding and 45 planned units. Stage 50 and stage 70 re-verify the frozen bytes.

## Limitations

- One incident and five deterministic repeats per cell: a feasibility study, not incident replication.
- The baseline uses the known injection time, so the test does not estimate unknown-onset detection. The
  workload is synthetic and steady; the anomaly score is a fixed evidence-construction step, identical for
  every model and input.
- The time-estimate outcome is fixed by design (its +20 s exceeds the post-damage tail).
- Exploratory tests are on acceptance; correctness differences (for example DeepSeek R2) appear in the
  descriptive tables only.

## Reproduction entry points

- Site configuration: `etc/lab.local.env` from `etc/lab.local.env.example`; every host-specific value
  (addresses, endpoints, names) is listed in the README site table.
- `bin/lab-p9-modelset --build --served-identities`, then `run/all.sh` (provisioning to analysis), or the
  stages one at a time. `run/dry-run.sh` rehearses stages 20 and 30 in a separate scope.
- Run outputs (`logs/`, `evidence/`, `archive/`, `results/`, `analysis-out/`) are local and not tracked. The
  study's records are kept in `records/P12/`; `python3 records/P12/verify.py` checks them against the freeze.

## Open operator decisions

- Publishing the repository and its records (nothing has been pushed).
- Whether any earlier development-lab restore stopped a source cluster through the defect fixed in
  c08df4f; restore outcomes are unaffected either way, since restores use clones and archived WAL.
