# Constitution Amendment 001 — Boundary integrity and verification tiers

**Status:** to be appended verbatim to `.specify/memory/constitution.md` by task R001, step 1.
**Raised by:** P0 acceptance review, 2026-08-17.
**Cause:** the P0 build shipped a test-only read hatch inside the component that implements the out-of-band
isolation boundary, and reported 18/18 acceptance criteria PASS when nine of those criteria were satisfied by
searching an agent-authored narrative file for a token.

Append the following two articles, and renumber nothing.

---

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
