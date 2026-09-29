# SDD Package, Tranche P3 (Derived Analytics & the Arm A Deterministic Ranker)

Same format as P0, P0.1, P1, P1.1, P2 and P2.1: **GitHub Spec Kit** layout, extended with a `work-instructions/`
tier below `tasks.md` that Spec Kit itself does not provide.

Unpack so it **merges into** the existing `<repo>/sdd`. Nothing under any prior `specs/*/` directory is
edited, and every prior frozen contract — including `capture-completeness.md` and its amendment — stays
byte-identical so its recorded hash keeps verifying. This tranche is the first that **consumes** the certified
ledger: it builds the deterministic detection and ranking layer whose output is the baseline arm of the experiment.

## Why this tranche exists

Everything upstream built and certified the evidence. **P3 is the first intelligence over it.** It delivers two of
the roadmap components:

- **C5 Derived analytics** — per-window change-burst density, per-relation and per-path churn, deletion-volume
  spikes, DDL flags, and mean-plus-3-sigma anomaly scoring against a declared quiescent baseline window, all computed
  over the ledger through the P2 DuckDB views, and all **provenance-blind**.
- **C7 Arm A deterministic ranker** — candidate recovery-coordinate generation and a deterministic ranking function
  with declared weights and tie-breaks, plus the **naive comparator** (last checkpoint before an approximate
  operator-supplied incident time, with a declared, fixed time error).

Arm A is the reproducible baseline the whole experiment is measured against: it is both the algorithmic comparator for
Arm B (the modest local model, P6) and the sanity oracle for the harness. Its headline job in P3 is to beat the
naive comparator on a real SC-01 incident, with both recovery-point errors landing in the results file automatically.

## The one rule that makes the result worth anything

**Provenance is for scoring, never for detection (Article II).** The ledger records which principal made each change
so the *oracle* (P1) can classify damage from legitimate work when it computes the ground-truth optimum. The
analytics and the ranker must **never** read that field. If detection can see who made a change, the task is trivial
and the result is worthless. P3 enforces this as a mechanical negative test: strip the provenance fields from the
view handed to C5 and C7, and the selected coordinate must not move.

A second, broader form of the same rule: the ranker may see only the provenance-blind ledger and an operator-supplied
approximate incident time. It must **not** read the injection log or the oracle's known optimum. Detection does not
get to peek at the answer.

## What P3 delivers

| # | Deliverable | Task |
| --- | --- | --- |
| 1 | Two frozen contracts: candidate-coordinate record schema (C5 out) and the shared Arm coordinate format (C7↔C8) | D001 |
| 2 | SC-01 realized as a reconciled incident: `bin/lab-inject-sc01` + concurrent repeated-key workload profile + oracle params | D002 |
| 3 | `bin/lab-analytics` — per-window burst density, per-relation/path churn, deletion spikes, DDL flags (provenance-blind) | D003 |
| 4 | mean+3σ anomaly scoring against the declared quiescent baseline window | D004 |
| 5 | `bin/lab-candidates` — candidate coordinate generation to the frozen schema | D005 |
| 6 | `bin/lab-rank` — the Arm A deterministic ranker with declared weights + tie-breaks | D006 |
| 7 | `bin/lab-naive` — the naive comparator with a declared, fixed incident-time error | D007 |
| 8 | Wiring Arm A + naive into the P1 `evaluate-arm` phase so both recovery-point errors auto-land in the results row | D008 |
| 9 | Headline test (Arm A beats naive on SC-01) + provenance-blindness + no-oracle-peek negative tests | D009 |
| 10 | `bin/lab-verify-p3` tiered gate; all prior contract hashes re-verified; P3 architecture handoff | D010 |

## Target environment

Unchanged and confirmed by the P0→P2.1 builds:

- Host `r740core`, Ubuntu 26.04 LTS, KVM, ext4 root. Agent has `sudo`.
- Victim guest `thesisvm01`, keyless SSH from host, agent has `sudo` inside.
- PostgreSQL 18.4, wal2json 2.6-3, ZFS 2.4.1-1ubuntu5, devices `/dev/vdb` + `/dev/vdc` guest-side.
- DuckDB as the read-only view layer (no new dependency; P3 adds no third-party runtime).
- Deploy root `<repo>`. Config `etc/lab.env`.
- Gates green: `lab-verify` **18/18**, `lab-verify-p1` **24/24**, `lab-verify-p1.1` **16/16**, `lab-verify-p2`
  **18/18**, `lab-verify-p2.1` **16/16**, all exit 0.

## Two entry conditions (do not skip)

1. `bin/lab-ready` exits 0 (ADR-P1.1-4), **and** the incident P3 analyses has passed `bin/lab-ledger-account`
   exactly-once (ADR-P2-7). P3 refuses to run detection over an unreconciled ledger.
2. The git working tree is clean before any provenance-bearing or results-bearing artefact is produced (Article XIV).

## Install

```bash
# on r740core, as mlasota
cd <repo>
# unpack this package so that it merges into ./sdd
```

## Run one task per invocation

```bash
cd <repo>
<executor> --print "$(cat sdd/prompts/execute-P3.md)

TASK_TO_EXECUTE: D001
MODE: DRY_RUN"
```

Review the dry-run bundle, then re-run with `MODE: EXECUTE`. Proceed `D001 → D010`, one task per call. **Do not batch
tasks** — batching lets the agent optimise across contract boundaries and is how a green self-report hid a real
defect four times already (the P0.1 hatch, the P1 `harness_commit`, the P2 `xid` substitution, and the reconciliation
soundness hole).
