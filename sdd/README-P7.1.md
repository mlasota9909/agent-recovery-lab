# SDD Package, Tranche P7.1 (Matrix Isolation: make the multi-scenario result real, not hollow)

Same format as P0..P7: **GitHub Spec Kit** layout, extended with a `work-instructions/` tier below `tasks.md` that
Spec Kit itself does not provide.

Unpack so it **merges into** the existing `/home/mlasota/thesis/sdd`. Nothing under any prior `specs/*/` directory is
edited, and no frozen contract file is mutated. This tranche repairs the P7 acceptance findings and closes the class
behind the most serious one with a new constitutional article.

## Why this tranche exists

P7 built the scenario harness and drove the matrix, and `bin/lab-verify-p7` closed 21/21. The **apparatus and the
reporting are sound** — the P7 handoff addendum discloses every deviation honestly, which is exactly the Article XVIII
behaviour the project was built to produce. But "honestly reported" and "scientifically clean" are different things,
and the acceptance review found three problems the gate could not catch, because the gate verifies mechanics and row
count, not experimental validity:

**D1 — the multi-scenario matrix is scientifically hollow, and the root cause is architectural.** T012
`zfs rollback -r` operates on the shared parent `DS_PARENT=labpool/victim`. The matrix evaluates three *live* incidents
(SC-02/03/04) on that one shared dataset. The first live T2 (SC-02 `post_capture`) **destroyed the later incidents'
snapshots** (SC-03/SC-04); the archive `snapshots.json` still listed them, live ZFS did not. The first unattended run
wrote 51 rows and completeness passed, but **all 34 SC-03/SC-04 cells were `run_failure`** ("target snapshot does not
exist"). Those 34 rows were then stripped so `total_rows` stayed 51 rather than 85 — completeness green over a matrix
that never ran. A shared mutable substrate cannot support independent experimental units.

**D2 — the new scenarios were never validated against ground truth.** SC-02/03/04 have no `oracle-manifest.json`, so
every Arm B determination came back `restore_verdict=stub`: the P4 restore-and-validate loop — the thing that made
SC-01 trustworthy by *actually restoring the chosen coordinate and diffing it against ground truth* — was skipped.
Coordinates were resolved from the **frozen archive** `snapshots.json` (`LAB_P7_HOST_COORD=1`, `resolved_by:
snapshot_first`), not live ZFS, so `skew_ms` was reported `0` for those cells (not a measurement — a consequence of the
resolve path). SC-02/03/04 are exploratory, not confirmatory.

**D3 — the SC-04 headline conflates two different claims and mislabels one of them.** `P7-handoff.json` carries
`sc04_headline.strongest_figure: true` with `matches_prediction: false`, `evidence_bytes_r2: 1099` vs
`evidence_bytes_r0: 799`, `token_r2: 302` vs `token_r0: 198`. Two distinct facts are entangled: (a) SC-04 is the
**strongest actionability result** — R2 achieved a 0.95-quality determination where R0 scored 0.0, the largest arm-
quality gap in the matrix; and (b) SC-04 **refutes the universal-compactness claim** — on a tiny 799-byte incident,
R2's graph+summary overhead made it *larger* than R0. Both are true and both are valuable, but `strongest_figure:
true` attached to a row where R2 loses on bytes will read as an error to anyone who opens the JSON. The two
dimensions must be disaggregated and stated honestly.

## What P7.1 delivers

| # | Deliverable | Closes |
| --- | --- | --- |
| 1 | New **Article XIX** — independent experimental units must be isolated on shared substrate; completeness is not validity; a unit that fails for infrastructural reasons is superseded (retained), never silently deleted | The hollow-matrix / stripped-rows class |
| 2 | **L001** root-cause diagnosis of the shared-pool destroy + a bounded **go/no-go decision** (FULL isolation re-run vs documented FALLBACK to SC-01-anchored preliminary), with ADR-P7.1-1..5 | D1 root cause + timeline protection |
| 3 | **`incident-isolation.md`** (new frozen contract): per-incident ZFS dataset subtree `labpool/victim/inc_<id>` with its own transient cluster; reset scoped to the incident subtree; `zfs rollback -r` on the shared parent forbidden | D1 fix |
| 4 | **`run-matrix-plan.amendment-1.md`** (Article XV supersession): live-coordinate resolution required for re-run cells; validity partition reported beside completeness; superseded rows retained with a `supersedes` pointer; real P4 validation where a single-coordinate oracle exists | D1/D2 |
| 5 | **L002** per-incident isolation + the sibling-safety negative test; **L003** oracle manifests + real validation; **L004** live re-run of SC-02/03/04 under isolation with superseded predecessors; **L005** honest disaggregated headline; **L006** gate + mapping + memo | D1/D2/D3 |

## Target environment

Unchanged and confirmed by the P0..P7 builds:

- Host `r740core`, Ubuntu 26.04 LTS, KVM, ext4 root. Agent has `sudo`.
- Victim guest `thesisvm01`, keyless SSH from host, agent has `sudo` inside.
- PostgreSQL 18.4, wal2json 2.6-3, ZFS 2.4.1-1ubuntu5, devices `/dev/vdb` + `/dev/vdc` guest-side, pool `labpool`.
- Arm B model (pinned in H001, amended P6.1): `gb10a-deepseek-v4-flash`, quant `exl3-k2`, 262,144-token context, greedy,
  via LiteLLM `http://c220m3:4001` fronting vLLM `gb10a:8000`. Cloud alias `deepseek-v4-pro` not used.
- Deploy root `/home/mlasota/thesis`. Config `etc/lab.env`.
- Gates today: `-p0` 18/18 ... `-p6` 19/19, `-p6.1` 16/16, `-p7` 21/21. Constitution: eighteen articles in force
  (Article XVIII = null results root-caused before reported); L001 adds the nineteenth.
- Canonical P7 incidents (from the addendum): SC-01 `SC-01_20260824T091611Z` (banked headline — **never re-run**),
  SC-02 `SC-02_20260826T095506Z`, SC-03 `SC-03_20260826T101320Z`, SC-04 `SC-04_20260826T101526Z`. SC-03/SC-04 live ZFS
  snapshots were destroyed by the shared-pool T2; only their archive records survive, so they are **regenerated once**
  under isolation in this tranche.

## Install

```bash
# on r740core, as mlasota
cd /home/mlasota/thesis
ls sdd/specs/P7.1-matrix-isolation/tasks.md   # sanity check
```

## Execute

One task per invocation, in order, dry run first. **Do not batch.** You are running this with the executor; the same
one-task-per-invocation discipline applies regardless of the agent.

```bash
cd /home/mlasota/thesis

<executor> "$(cat sdd/prompts/execute-P7.1.md)

TASK_TO_EXECUTE: L001
MODE: DRY_RUN"

<executor> "$(cat sdd/prompts/execute-P7.1.md)

TASK_TO_EXECUTE: L001
MODE: EXECUTE"
```

Order: `L001 -> L002 -> L003 -> L004 -> L005 -> L006`. `L006` is the gate and runs last. `L002/L003` may run in either
order after L001; both precede `L004`.

## The decision that governs the tranche

**L001 ends in a recorded go/no-go.** This tranche attempts the real fix — per-incident isolation and a live,
validated re-run — because that is what turns SC-02/03/04 from exploratory into confirmatory. But L001 must first prove
per-incident isolation is buildable and that a re-run fits the remaining time budget. If it is not, L001 records
**FALLBACK**: SC-01 remains the sole validated headline, SC-02/03/04 are presented as clearly-bounded preliminary
findings with D2/D3 corrected in documentation only, and L002–L004 are marked not-executed with the reason. This is the
timeline guard — do not spend the writing weeks chasing a clean matrix if isolation proves costly. The operator
countersigns the decision before L002 begins.

## What you review after each task

Open `sdd/specs/P7.1-matrix-isolation/work-instructions/WI-Lnnn.md`, read its *Review bundle* and *Operator review
checklist*, then check `/home/mlasota/thesis/logs/review/Lnnn/` exists and its `acceptance.md` rows are tier-labelled
per Article XIII. Tick the row in `checklist.md` yourself — the agent does not own the `Reviewed` column.

The task to read line by line is **L002**, because the sibling-safety negative test (reset one incident, prove another
incident's snapshots and heartbeat survive byte-identical) is the assertion that proves the root cause is actually
fixed rather than worked around.

## Anti-goals

Do not, in P7.1: re-run or regenerate the SC-01 headline incident (it is banked and byte-frozen — its `db.jsonl` and
`results/SC-01.jsonl` hashes must re-verify); edit any frozen contract file (supersede by amendment instead);
lower Arm A's 3σ threshold to manufacture a hit (SC-02's `run_failure` for want of a 3σ window is a genuine finding —
report it, do not patch it); delete or hide a `run_failure` or refusal row to make completeness look better (supersede
and partition instead — Article XIX); resolve re-run coordinates from the frozen archive when a live incident cluster
exists (that was the D2 defect); invent an SC-01 oracle manifest for a different scenario; read `principal` in any path
(Article II); change the model pin or the representations; make a gate pass by weakening what it checks. If a task
appears to require one of these, it has been misread.
