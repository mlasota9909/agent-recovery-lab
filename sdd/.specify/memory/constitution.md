# Constitution — Recovery-Point Experiment

Non-negotiable principles. Every spec, plan, task and work instruction is checked against this file. A change here
requires an explicit dated amendment at the bottom. Where a principle and a convenience conflict, the principle wins.

## Article I — Determinism in the measured path

All recovery-point selection, scoring and ground-truth adjudication MUST be deterministic and reproducible from
stored evidence. Re-running an evaluation over the same frozen incident MUST produce a byte-identical result row
except for wall-clock duration fields.

No language model may participate in candidate generation, ranking or selection in the measured path. Model use is
confined to producing operator-facing natural-language explanation, and (in the ablation arms) to answering a
selection question whose accuracy is *measured against* the deterministic result.

## Article II — Provenance is for scoring, never for detection

The evidence store records which principal caused each change (`lab_app` vs `lab_agent`). This exists so the
ground-truth oracle can score. The analysis engine, the representation builders and any model MUST NOT read
provenance fields. Every analysis component MUST be exercised by a negative test: strip provenance from its input
view and assert the selected coordinate does not change. Leaking provenance into detection invalidates the entire
experiment.

## Article III — Evidence is out-of-band, append-only, immutable

The evidence store, the WAL archive and the results store live on the host, outside `thesisvm01`. The victim has
exactly one narrow append path outward (the WAL archive sink) and it MUST refuse overwrite. No victim principal may
read, list, modify or delete evidence. Evidence files, once closed, are read-only (mode 0444).

## Article IV — CLI-first, text in, JSON out

Every capability ships as a CLI under `<repo>/bin/`. Each accepts arguments and/or stdin, emits JSON
on stdout, emits human log lines on stderr, and returns non-zero on failure. No capability may exist only as an
importable function, a notebook cell, or an interactive step. If it cannot be invoked from a batch script it does
not exist.

## Article V — Stock mechanisms only; named prohibitions

Use the platform's own facilities. The following are explicitly PROHIBITED in this project:

- writing a WAL parser, or building any analysis on `pg_waldump` output
- a live filesystem event daemon (`fanotify`/`inotify`) for evidence capture
- `zfs send`/`zfs receive` plumbing, clones or loop mounts for reading past state
- any bespoke database server, message broker or job queue
- ORMs, web frameworks or service daemons in the harness

Filesystem change evidence comes from `zfs diff` and `.zfs/snapshot/`. Database change evidence comes from logical
decoding via `wal2json`. Recovery comes from base backup plus archived WAL. Nothing else.

## Article VI — Simplicity and anti-abstraction

No component, layer, abstraction or dependency may exist unless a named acceptance criterion in a `spec.md` requires
it. Maximum three runtime languages: POSIX shell, SQL, Python 3. Prefer a 20-line script in `bin/` over a package.
Do not build configuration systems: there is exactly one config file, `etc/lab.env`, and it is flat `KEY=value`.

## Article VII — Frozen contracts

Files under `specs/*/contracts/` are contracts. Once a tranche is accepted, a contract changes only by explicit
amendment, never by a downstream task widening a field in passing. Two contracts are load-bearing across the whole
project: the recovery **coordinate triple** (wall clock, LSN, snapshot) and, from P1, the **results row**.

## Article VIII — Fail loud

No silent degradation, no fallback that hides a missing precondition, no `|| true` on a check, no invented default
for a value that should have been discovered. If a precondition is absent the tool exits non-zero with a message
naming the precondition. A check that cannot fail is worthless: security and isolation tests MUST include a
deliberate-regression case proving the check detects a violation.

## Article IX — Traceability

Every task states the scenario and research question it serves. Every acceptance test names the
requirement it discharges. An artefact that traces to nothing gets deleted, not kept "just in case".

## Article X — Lab containment and ethics

All data is synthetic and generated in-lab. No production data, no personal data, no third-party data. No component
makes outbound network calls at experiment time; models run locally. Destructive activity is confined to
`thesisvm01`. The host's own filesystem outside `<repo>` is never written to.

## Article XI — Evidence of work

Every task produces a review bundle under `logs/review/<task-id>/` containing the commands run, their captured
output, and the acceptance-test results. A task is not complete because the agent says so; it is complete when the
bundle exists and its assertions pass.

---
Ratified 2026-08-17. Amendments: 001 (2026-08-17) — Articles XII, XIII. 002 (2026-08-21) — Article XIV. 003 (2026-08-24) — Article XV.

## Article XII — No test hatches in boundary components

A *boundary component* is any component whose correctness constitutes a security, isolation or containment claim
of the experiment. In this project that means at minimum: the WAL append channel and its forced command, the SSH
authorised-key configuration for victim principals, the evidence-root permission model, and the reset tooling.

Boundary components MUST NOT contain any code path that widens the boundary and is enabled by a test flag, an
environment variable, a sentinel file, a debug argument or a magic command string. This prohibition applies
**regardless of the path's default state**. A closed door with a hinge is still a door.

Negative and regression tests for a boundary MUST be implemented **outside the component under test**, by mutating
state that the component does not itself read — for example host-side file permissions, ownership, or SSH
authorised-key entries. A regression test that works by asking the component to misbehave proves only that the
component can be asked to misbehave.

Every boundary component MUST be covered by a **command-surface enumeration test**: a fixed corpus of candidate
invocations is presented to the component, and the test asserts that exactly the intended invocation class succeeds
and every other invocation is refused with a non-zero exit. Adding a hatch then breaks the enumeration test, which
is the point.

## Article XIII — Verification tiers

Every acceptance criterion carries a tier:

- **Tier M (mechanical).** Re-derived at verification time from live system state or from committed machine-readable
  artefacts. Passes or fails on its own evidence, with no reference to any narrative written by an implementer.
- **Tier A (attested).** Satisfied by a recorded observation of a one-time event that cannot be cheaply re-derived.
  A tier A criterion MUST still assert on a **machine-readable field** in a committed artefact — a key in
  `etc/lab.env`, a field in a JSON file, an exit code in a captured log. It MUST NOT be judged by the presence or
  absence of a token, word or phrase in prose.

Any acceptance criterion that is load-bearing for a research claim MUST be tier M.

The full acceptance runner MUST print the tier alongside each criterion and MUST print separate totals per tier. A
single undifferentiated "18/18 PASS" is prohibited, because it conceals how much of the suite is self-attestation.

---
Amendment 001 ratified 2026-08-17.

## Article XIV — Provenance of record

Any artefact that records the identity of the code, data or configuration that produced an experimental result must name the exact state that produced it, re-derived at production time. Where that state is versioned, the recorded identity must be the version-control HEAD at production time, and the producer must refuse to emit a result when the tracked tree has uncommitted changes. A provenance field that can name a state other than the one that produced the artefact is a defect regardless of whether it is currently accurate.

---
Amendment 002 ratified 2026-08-21.

## Article XV — Amendment of frozen artefacts

When implementation reveals that a frozen contract cannot be honoured exactly as written, the contract MUST NOT be silently deviated from, nor mutated in place. The original file MUST remain byte-identical so its recorded hash continues to verify. The change MUST be recorded as a superseding amendment: a separate, sequentially-numbered document that names the exact clause it supersedes, is itself hash-frozen, and references an ADR stating the technical reason. Every consumer of the contract MUST read the contract together with its amendments. A deviation from a frozen contract that is neither reflected in a frozen amendment nor caught by the acceptance gate is a defect of the same class as a silent test hatch (Article XII).

---
Amendment 003 ratified 2026-08-24.

## Article XVI — Read-only verification gates

A verification gate (`bin/lab-verify*`, `bin/lab-regression`, `bin/lab-gate-readonly-check`, and any future acceptance check) MUST NOT create, modify, move, change the mode of, or delete any artefact under the evidence root. It reads evidence and writes only under `logs/review/`. Where a check needs a mutable copy of an artefact, it copies into `logs/review/<id>/scratch/` and operates there. Read-only behaviour MUST be mechanically enforced (a before/after evidence manifest), not merely asserted. A gate that mutates the evidence it certifies is a defect of the same class as a silent test hatch (Article XII).

---
Amendment 004 ratified 2026-08-24.

## Article XVII — Subject-visible surface excludes the reference answer

Where an experiment measures whether a subject (a model, a ranker, a human) can *derive* an answer from evidence, the bytes presented to that subject MUST NOT contain the reference answer, the ground-truth coordinate, or any pre-computed result the experiment is testing the subject's ability to produce. The subject-visible surface (the "model view") is defined explicitly and separately from the reference answer used to score or to check parity. This separation MUST be mechanically enforced (a guard that inspects the subject-visible bytes and refuses any that carry the answer), not merely documented. Presenting the answer alongside the evidence a subject reads is a defect of the same class as a silent test hatch (Article XII) and a provenance leak (Article II).

---
Amendment 005 ratified 2026-08-25.

## Article XVIII — Null results are root-caused before they are reported

A null, empty, or degenerate experimental result (no signal, total refusal, all-zero, or a single-valued outcome) MUST NOT be reported as a finding about the subject until its proximate cause has been established from primary evidence (the raw outputs, not a summary) and the instrument — the harness, the prompt, the extraction grammar, the measurement path — has been ruled out as the cause or corrected. A green gate that verifies mechanics and honestly records the null does not discharge this obligation. Where the instrument is corrected, the result is re-derived; where the null survives a corrected instrument, it is a genuine finding and is reported as such, with the diagnosis that establishes it.

This sits alongside Article XII (no test hatches), XIII (verification tiers), XIV (provenance of record), XV (amendment of frozen artefacts), XVI (read-only gates) and XVII (subject-visible surface excludes the answer) as the seventh lesson learned from review, each closing a class rather than an instance.

---
Amendment 006 ratified 2026-08-26.

## Article XIX — Independent units are isolated; completeness is not validity.

When an experiment comprises multiple independent units (incidents, scenarios, trials) over shared mutable
infrastructure, each unit MUST be isolated so that operating on one cannot destroy or alter the recorded state of
another. A completeness metric (produced count == planned count) MUST NOT be reported as evidence the experiment ran;
it MUST be accompanied by a validity partition that separates genuine outcomes from harness/infrastructure failures,
each failure carrying a diagnosed cause. A unit that fails for infrastructural reasons MUST be recorded as superseded
— retained with a pointer to its replacement — never silently removed to keep a completeness metric green.

---
Amendment 007 ratified 2026-08-27. Amendment 008 (2026-08-28) — Article XX.

## Article XX — Bounded standing authority; resolve, record, continue

The agent is the architecture authority for internal, in-lab, reversible decisions. The
default is to RESOLVE and CONTINUE, not to halt and hand off. Halting mid-run for a decision
the agent is authorized to make is itself a process failure.

### XX.1 Resolve autonomously (do not stop)
When a blocker is an internal contradiction between two project documents, a missing
regenerable artifact, hash drift, or an out-of-date gate pin, the agent resolves it itself
using this precedence:

    constitution  >  frozen contract + its amendments  >  spec/plan  >  work instruction  >  convenience

The agent MUST prefer the least-breaking, backward-compatible option so historical evidence
stays valid and no migration is required. It then records an ADR plus a hash-frozen
superseding amendment (Article XV), re-pins any derived hashes, adds the required negative
test (Articles VIII/XII/XIII), and CONTINUES.

### XX.2 Stop and escalate only for these
1. The action is destructive outside the lab, touches the host outside
   `<repo>`, or risks real / production / personal data.
2. The only way forward would falsify a recorded experimental result, relabel evidence
   dishonestly, drop a unit to keep a metric green (Article XIX), or read provenance into a
   detection path (Article II).
3. The contradiction has no backward-compatible, traceable resolution — every option breaks
   a frozen hash with no valid amendment path, or forces migration that could invalidate
   banked results.
4. It needs a new external resource, credential, endpoint, or human approval that cannot be
   obtained in-lab.

### XX.3 Batching rule
Never halt mid-run for anything outside XX.2. Accumulate non-blocking notes, decisions made,
and review requests into a single `logs/review/<tranche>/decision-log.md` presented at the
END of the run. One review at the end, not a handoff every few minutes.

### XX.4 Logging rule
Every autonomous architecture decision produces an ADR + amendment + updated gate, so it is
auditable and reversible. A decision recorded and continued is the goal; a decision escalated
and stalled is the failure mode this article exists to prevent.

---
Amendment 008 ratified 2026-08-28.

## Article XXI — Pre-registered analysis; report what it shows

1. Any tranche that draws an inferential or comparative conclusion from experimental
   data MUST freeze its statistical analysis plan BEFORE data collection for that
   tranche begins. The frozen plan names: the outcome metric(s), the unit of pairing,
   the specific test(s), the effect-size measure, the multiple-comparison correction,
   and the pre-declared interpretation for each possible outcome (including the outcome
   that contradicts the tranche's hypothesis).

2. The analysis plan is a frozen contract under Article XV. Its digest is pinned. The
   analysis step MUST refuse to run if the plan's digest changed after the first data
   row was generated. Adding a post-hoc analysis is permitted ONLY as an explicitly
   labelled "exploratory (not pre-registered)" section that cannot override the
   pre-registered conclusion.

3. Results MUST be reported whatever they show. A tranche MAY NOT be reframed, its
   metric swapped, or units dropped to convert an unfavourable result into a favourable
   one. An unfavourable-but-honest result is an acceptable and complete outcome
   (this composes with Articles XVIII and XIX).

4. Rationale: a statistics-bearing tranche introduces a p-hacking / selective-reporting
   failure class. Pre-registration closes that class the way prior articles closed the
   hatch (XII), provenance (XIV), and hollow-completeness (XIX) classes.

---
Amendment 009 ratified 2026-09-01. Article XXI — pre-registered analysis (P9 N001).
