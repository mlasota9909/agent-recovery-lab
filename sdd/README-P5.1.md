# SDD Package, Tranche P5.1 (Model-View Separation: the subject must not be handed the answer)

Same format as P0, P0.1, P1, P1.1, P2, P2.1, P3, P3.1, P4 and P5: **GitHub Spec Kit** layout, extended with a
`work-instructions/` tier below `tasks.md` that Spec Kit itself does not provide.

Unpack so it **merges into** the existing `<repo>/sdd`. Nothing under any prior `specs/*/` directory is
edited, and no frozen contract file is mutated. This tranche repairs one latent confound found in the P5 acceptance
review, and closes the class behind it with a new constitutional article.

## Why this tranche exists

P5 delivered the three representations (R0 flat log, R1 temporal aggregates, R2 deterministic graph + summaries)
behind one query interface, and its work is genuine: R2 is deterministically built (`built_by_model=false`,
reconciled against the ledger), the representations are provenance-blind, and R2's evidence-bytes on the recovery
probe are a small fraction of R0's. `bin/lab-verify-p5` closed green.

But the review found a latent confound that would silently void the entire P5→P6 contribution. In the frozen
`representation-interface` contract, the response envelope co-locates two things:

- `content` — the evidence the representation surfaces, which the model is *supposed* to read and reason over; and
- `answer` — the structured, pre-computed result, which for the recovery probe `PB-6-candidate-windows` **is the
  recovery coordinate itself** (`candidates:[{window_index, last_safe_lsn_int, anomaly_score}]`), computed by the
  deterministic pipeline and **identical across R0/R1/R2**.

P6 is meant to point a modest local model at a representation and have it *derive* the coordinate, with R2 letting it
succeed on far fewer tokens — that delta is the research question. But nothing mechanically stops P6 from passing the whole
response envelope, `answer` included, to the model. If it does, the model reads the coordinate for free from `answer`,
the representation `content` becomes decorative, and the R0-vs-R1-vs-R2 ablation measures nothing. The contract's own
§5 even designates PB-6 as "the one P6's model uses to locate a recovery coordinate" — so the answer key sits in the
envelope for precisely the probe where it does the most damage.

This is the same class that has recurred through the build: an **unenforced separation between what a subject may see
and the answer key** — the P0.1 test hatch, the P3 provenance-in-detection, the P1 `harness_commit`, the P2 `xid`. Each
stayed shut only by discipline until a gate forced it. P5.1 forces this one before P6 depends on it.

To be fair to P5: keeping a representation-independent `answer` is *useful* as an internal parity reference — it
confirms all three representations are asked to support the same result. The flaw is only that it lives in the
model-facing envelope with no barrier. P5.1 does not delete it; it moves it out of the subject-visible surface.

## What P5.1 delivers

| # | Deliverable | Closes |
| --- | --- | --- |
| 1 | New **Article XVII** — the subject-visible surface must exclude the reference answer | The answer-key-in-the-subject-view class |
| 2 | **ADR-P5.1-1** recording the confound; **ADR-P5.1-2** the `model_view`/`reference` split; **ADR-P5.1-3** the guard mechanism | Governance + design |
| 3 | **`representation-interface.amendment-1.md`** (Article XV supersession): splits `model_view` (the only object P6 may pass to a model) from `reference` (the `answer`, used solely by parity/telemetry tests). Original contract file stays byte-identical | The interface split |
| 4 | `bin/lab-repr-modelview` (emits only the model-visible surface) and `bin/lab-modelview-guard` (mechanically refuses any model view carrying `answer`/a coordinate result/a provenance token), with a negative test | Enforcement |
| 5 | Parity re-scoped to the model-visible surface; the F009 headline relabelled to **PB-6** (the recovery probe); `bin/lab-verify-p5` re-derived to honest green; R0/R1/R2 artefacts proven byte-identical to their P5 close; `bin/lab-verify-p5.1` gate + criterion mapping + memo | All |

## Target environment

Unchanged and confirmed by the P0..P5 builds:

- Host `r740core`, Ubuntu 26.04 LTS, KVM, ext4 root. Agent has `sudo`.
- Victim guest `thesisvm01`, keyless SSH from host, agent has `sudo` inside.
- PostgreSQL 18.4, wal2json 2.6-3, ZFS 2.4.1-1ubuntu5, devices `/dev/vdb` + `/dev/vdc` guest-side.
- Deploy root `<repo>`. Config `etc/lab.env`.
- Gates today: `bin/lab-verify` 18/18, `-p1` 24/24, `-p1.1` 16/16, `-p2` 18/18, `-p2.1` 16/16, `-p3` 19/19 (after P3.1),
  `-p3.1` 16/16, `-p4` 19/19, `-p5` 19/19.
- `bin/lab-ready` exits 0. Constitution: sixteen articles in force (Article XVI = read-only gates); G001 adds the seventeenth.

## Install

```bash
# on r740core, as mlasota
cd <repo>
# unpack this package so that it merges into ./sdd
ls sdd/specs/P5.1-modelview-separation/tasks.md   # sanity check
```

## Execute

One task per invocation, in order, dry run first. **Do not batch.**

```bash
cd <repo>

# read-only dry run, changes nothing
<executor> --print "$(cat sdd/prompts/execute-P5.1.md)

TASK_TO_EXECUTE: G001
MODE: DRY_RUN"

# then for real
<executor> --force "$(cat sdd/prompts/execute-P5.1.md)

TASK_TO_EXECUTE: G001
MODE: EXECUTE"
```

Order: `G001 -> G002 -> G003 -> G004`. `G004` is the gate and runs last.

## What you review after each task

Open `sdd/specs/P5.1-modelview-separation/work-instructions/WI-Gnnn.md`, read its *Review bundle* and *Operator review
checklist*, then check `<repo>/logs/review/Gnnn/` exists and its `acceptance.md` rows are tier-labelled
per Article XIII. Tick the row in `checklist.md` yourself — the agent does not own the `Reviewed` column.

The task worth reading line by line is **G002**, because it decides what P6 is allowed to hand the model. If the
`model_view` still carries the coordinate, the whole P5→P6 comparison is void.

## Anti-goals

Do not, in P5.1: change any frozen contract file (supersede by amendment instead); add a field to any results,
ledger, candidate, arm-coordinate, or representation contract; rebuild or re-fit the R0/R1/R2 representation artefacts
(they are sound — P5.1 changes the interface surface, not the representations); re-run the SC-01 headline to change its
numbers (only relabel which probe is reported); invoke a language model anywhere (Article I); read `principal` in any
path (Article II); make a gate pass by weakening what it checks (a gate becomes *correctly targeted*, never *less
strict*). If a task appears to require one of these, it has been misread.
