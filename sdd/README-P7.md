# SDD Package, Tranche P7 (Scenario expansion and the run matrix)

Same format as P0 through P6.1: **GitHub Spec Kit** layout, extended with a `work-instructions/` tier below
`tasks.md` that Spec Kit itself does not provide.

Unpack so it **merges into** the existing `<repo>/sdd`. Nothing under any prior `specs/*/` directory is
edited, and every prior frozen contract — including `capture-completeness.md`, `representation-interface.md` and its
amendment-1, `arm-b-protocol.md` and its amendment-1, and `model-runtime.md` and its amendment-1 — stays byte-identical
so its recorded hash keeps verifying.

## Why this tranche exists — from one scenario to the matrix

P3 realized SC-01 as a reconciled incident and produced Arm A and the naive comparator. P4 closed the restore+validate
loop. P5/P5.1 built the three representations behind the guarded `model_view`. P6/P6.1 ran Arm B on SC-01 and, after
the null was root-caused (Article XVIII), produced the honest R0-vs-R1-vs-R2 headline on that one scenario.

**P7 turns that single result into the experiment.** It implements SC-02 (filesystem mass deletion), SC-03 (schema
damage by staged DDL) and SC-04 (stealthy slow corruption) against the existing harness, adds the timing-pattern
variants, defines a stratified run plan with per-cell replicate counts based on **re-measured** throughput, and
executes the whole matrix unattended — one schema-valid results row per run. SC-01's banked cells (P3 Arm A/naive,
P6.1 Arm B) are included **by reference**; the frozen SC-01 headline ledger is never re-run or disturbed.

SC-04 is the point of the whole experiment: no burst, no obvious incident time, so a flat log cannot surface the signal
and only the temporal ledger and the graph-plus-summaries can. It is where the R0-vs-R2 gap should be largest and is
the strongest single result.

## The honest-reporting obligations that define P7

Two scenarios deliberately break the "one clean recovery coordinate" assumption, and reporting that honestly is a
first-class requirement, not an inconvenience:

1. **SC-03** — restoring to the LSN before the first destructive DDL also discards the legitimate DML committed during
   the migration window. P7 measures **both** the single-coordinate optimum and the legitimate work that a
   single-coordinate restore sacrifices. That trade-off is the selective-recovery future-work hook, stated plainly.
2. **SC-04** — there is no single coordinate that removes all corruption while retaining all legitimate work. The
   ground truth is the exact set of corrupted rows and the earliest malicious commit. P7 measures **precision and
   recall of identified malicious transactions** and the **earliest correctly-bounded malicious commit**, not a single
   pass/fail restore point.

A residual refusal or a null cell is root-caused via the Article XVIII taxonomy from the verbatim completions before it
is reported — never presented as a bare finding.

## The two properties carried in that P7 must not weaken

1. **The confounder is mandatory (roadmap risk).** Every scenario runs concurrent legitimate activity overlapping the
   damage window; a scenario without it makes detection trivial and is refused. This is what makes the recovery-point
   problem real.
2. **Provenance is for scoring, never detection (Article II).** The ledger records which principal made each change so
   the oracle can score, but no arm — deterministic or model — may read it. Every arm-coordinate carries
   `selection_inputs.read_*` all false; the model sees only the guarded `model_view`.

## What P7 delivers

| # | Deliverable | Task |
| --- | --- | --- |
| 1 | Two frozen contracts: `scenario-definition.md` (the machine-checkable scenario schema, incl. corpus citation) and `run-matrix-plan.md` (stratified per-cell replicate counts from re-measured throughput); the entry gate | K001 |
| 2 | SC-02 filesystem mass-deletion scenario: injector + build-and-edit confounder + oracle (tightest CoW snapshot before damage) + checkpoint-granularity gap | K002 |
| 3 | SC-03 schema-damage scenario: staged-DDL injector + interleaved DML confounder + oracle (LSN before first destructive DDL) + single-coordinate trade-off measure | K003 |
| 4 | SC-04 stealthy-corruption scenario: randomized small-UPDATE injector + high-volume legit-update confounder + oracle (corrupted-row set + earliest malicious commit) + precision/recall harness | K004 |
| 5 | Per-scenario R0/R1/R2 representations (reuse P5 builder), admissible + interface-parity + guard-clean; SC-01 artefacts/banked results re-verified unchanged | K005 |
| 6 | `bin/lab-matrix` — the unattended orchestrator: reset tiers between runs, incident-scoped, one schema-valid results row per run, ledger idempotency per incident | K006 |
| 7 | Execute the stratified matrix across scenario × timing × arm × representation × replicate; complete results file; a failed run records a failure row and the matrix continues | K007 |
| 8 | Honest-findings computation: SC-03 trade-off, SC-04 precision/recall + earliest-bounded commit, residual refusals diagnosed via Article XVIII | K008 |
| 9 | **Matrix headline:** cross-scenario R0-vs-R1-vs-R2 + Arm A vs Arm B vs naive from machine-readable fields; SC-04 the strongest figure | K009 |
| 10 | `bin/lab-verify-p7` tiered read-only gate; prior hashes re-verified; regression; P7 handoff | K010 |

## Target environment

Unchanged from the P0->P6.1 builds:

- Host `r740core`, Ubuntu 26.04 LTS, KVM, ext4 root. Agent has `sudo`.
- Victim guest `thesisvm01`, keyless SSH from host, agent has `sudo` inside.
- PostgreSQL 18.4, wal2json 2.6-3, ZFS 2.4.1-1ubuntu5, devices `/dev/vdb` + `/dev/vdc` guest-side.
- One offline local model (qwen-family, pinned in H001, greedy+seed+weights hash) reached over the private-lab
  endpoint recorded in `model-runtime.amendment-1` (P6.1): private network, no public egress, pinned local alias.
- Deploy root `<repo>`. Config `etc/lab.env`.
- Gates green: `lab-verify` 18/18, `-p1` 24/24, `-p1.1` 16/16, `-p2` 18/18, `-p2.1` 16/16, `-p3` 19/19, `-p3.1`
  16/16, `-p4` 19/19, `-p5` 19/19, `-p5.1` 16/16, `-p6` 19/19, `-p6.1` 16/16, all exit 0.
- **Eighteen** constitutional articles in force (through Article XVIII, null results root-caused before reported).

## Entry conditions (do not skip)

1. **P7 generates new incidents (SC-02/03/04), so it needs a healthy live lab to capture them.** Unlike P6, the entry
   gate requires `bin/lab-ready` to reach exit 0 for incident generation — but the **frozen SC-01 headline ledger must
   stay byte-identical** and its banked results untouched. New incidents get new incident ids and new paths; SC-01 is
   referenced, never regenerated. Manage the `archive/current` pointer per incident (the P0 timeline-reuse finding).
2. `bin/lab-regression` green against pinned fixtures; SC-01 R0/R1/R2 admissible and banked SC-01 results present.
3. The offline model runtime healthy and provably contained per the P6.1 containment redefinition.
4. The git working tree clean before any provenance-bearing or results artefact (Article XIV).

## Run one task per invocation

```bash
cd <repo>
<executor> --print "$(cat sdd/prompts/execute-P7.md)

TASK_TO_EXECUTE: K001
MODE: DRY_RUN"
```

Review the dry-run bundle, then re-run with `MODE: EXECUTE`. Proceed `K001 -> K010`, one task per call. **Do not batch
tasks** — batching lets the agent optimise across boundaries and is how a green self-report hid a real defect in
earlier tranches (the P0.1 hatch, the P1 `harness_commit`, the P2 `xid` substitution, the P3 impossible-green
regression, the P5 answer co-mingled with the model input, the P6 null-through-a-green-gate).
