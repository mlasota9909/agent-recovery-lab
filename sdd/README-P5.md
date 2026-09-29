# SDD Package, Tranche P5 (Representations R0 / R1 / R2 & the Identical Query Interface)

Same format as P0 through P4: **GitHub Spec Kit** layout, extended with a `work-instructions/` tier below `tasks.md`
that Spec Kit itself does not provide.

Unpack so it **merges into** the existing `<repo>/sdd`. Nothing under any prior `specs/*/` directory is
edited, and every prior frozen contract — including `capture-completeness.md` and its amendment — stays byte-identical
so its recorded hash keeps verifying.

## Why this tranche exists — this is where the contribution lives

Everything upstream built and certified the apparatus: the exactly-once evidence ledger (P2/P2.1), the deterministic
detection-and-ranking layer (P3), and the restore+validate loop that turns a coordinate into a scored, ground-truth
verdict (P4). **P5 builds the thing the experiment is actually about.**

The research claim is *not* that snapshots, WAL or PITR are novel — they are commodity substrate. The claim is that a
**purpose-built change representation** is what makes recovery-point identification tractable for a *modest local
model*: the representation, not the model size, does the work. P5 builds three representations of one certified
ledger and puts them behind **one query interface that is identical across all three**, so that in P6 a model can be
pointed at R0, R1 or R2 and cannot tell which it is talking to except by the content it receives. That identical
interface is what makes the R0-vs-R1-vs-R2 ablation clean.

- **R0** — flat chronological event log. The naive representation: the whole stream, in order.
- **R1** — structured temporal ledger with derived per-window aggregates.
- **R2** — a causal graph (sessions, transactions, relations, rows, files, processes; edges caused-by / modified /
  precedes / depends-on) plus hierarchical per-window and per-entity **summaries**, GraphRAG-style — but
  **deterministically constructed**, never model-generated.

## The two properties that make or break the contribution

1. **Identical query interface (ablation cleanliness).** All three answer the *same fixed probe set* through the
   *same request/response envelope*. Only the `content` returned and the telemetry differ. If the interface differs
   structurally, a P6 result could be explained by the interface rather than the representation, and the ablation is
   worthless. Asserted mechanically in F007.
2. **Deterministic construction, no model in the loop (R2 soundness).** The R2 graph and its summaries are
   deterministic functions of the ledger — fixed rules and template-rendered text, byte-identical on rebuild. Nothing
   is learned and no model writes a summary. So the question "how does R2 generalise from its
   training data?" does not arise — there is no training data. Asserted in F004/F006.

Two supporting properties are equally load-bearing: **fidelity** (a representation may neither fabricate nor omit
evidence — R1 aggregates and R2 summaries reconcile exactly to the R0/ledger counts, so a representation cannot "win"
by hiding the damage or inventing an anomaly) and **provenance-blindness** (no `principal`/`usename`/`session_user`/UID
anywhere in any representation or response — Article II; the model must not be able to read who made a change).

## What P5 delivers

| # | Deliverable | Task |
| --- | --- | --- |
| 1 | Two frozen contracts: `representation-interface.md` (the identical query interface) and `representation-fidelity.md` (determinism / completeness / reconciliation / blindness) | F001 |
| 2 | `bin/lab-repr-r0` — flat chronological event-log serialisation from the provenance-blind ledger | F002 |
| 3 | `bin/lab-repr-r1` — structured temporal ledger with derived per-window aggregates | F003 |
| 4 | `bin/lab-repr-r2` — deterministic causal graph + hierarchical per-window/per-entity summaries | F004 |
| 5 | `bin/lab-repr-query` — the single query interface, identical across R0/R1/R2, with per-probe telemetry | F005 |
| 6 | Determinism + fidelity + provenance-blindness verification across all three | F006 |
| 7 | The identical-interface property, asserted by a parity test | F007 |
| 8 | Telemetry: exact `evidence_bytes` and a declared-tokenizer `token_estimate` per probe, wired to the results row | F008 |
| 9 | Headline: SC-01 recovery-location probe answered faithfully by all three, with the R0-vs-R2 evidence-bytes delta | F009 |
| 10 | `bin/lab-verify-p5` tiered read-only gate; prior hashes re-verified; regression; P5 handoff | F010 |

## Target environment

Unchanged and confirmed by the P0->P4 builds:

- Host `r740core`, Ubuntu 26.04 LTS, KVM, ext4 root. Agent has `sudo`.
- Victim guest `thesisvm01`, keyless SSH from host, agent has `sudo` inside.
- PostgreSQL 18.4, wal2json 2.6-3, ZFS 2.4.1-1ubuntu5, devices `/dev/vdb` + `/dev/vdc` guest-side.
- DuckDB as the read-only view/query layer over the ledger. **P5 adds no new third-party runtime**: representations are
  built with stock Python 3 + DuckDB SQL; the token estimate uses a single vendored, pinned tokenizer (no model).
- Deploy root `<repo>`. Config `etc/lab.env`.
- Gates green: `lab-verify` **18/18**, `-p1` **24/24**, `-p1.1` **16/16**, `-p2` **18/18**, `-p2.1` **16/16**,
  `-p3` **19/19**, `-p3.1` **16/16**, `-p4` **19/19**, all exit 0.
- Sixteen constitutional articles in force (through Article XVI, read-only verification gates).

## Entry conditions (do not skip)

1. `bin/lab-ready` exits 0 **and** the SC-01 incident P5 represents has passed `bin/lab-ledger-account` exactly-once.
   P5 builds representations only from a reconciled ledger.
2. The git working tree is clean before any provenance-bearing or fidelity-manifest artefact is produced (Article XIV).
3. Representations are built from the **default provenance-blind ledger view only** — never a view that exposes the
   principal (Article II). F001 records which view that is.

## Run one task per invocation

```bash
cd <repo>
<executor> --print "$(cat sdd/prompts/execute-P5.md)

TASK_TO_EXECUTE: F001
MODE: DRY_RUN"
```

Review the dry-run bundle, then re-run with `MODE: EXECUTE`. Proceed `F001 -> F010`, one task per call. **Do not batch
tasks** — batching lets the agent optimise across boundaries and is how a green self-report hid a real defect in
earlier tranches (the P0.1 hatch, the P1 `harness_commit`, the P2 `xid` substitution, the P3 impossible-green
regression).
