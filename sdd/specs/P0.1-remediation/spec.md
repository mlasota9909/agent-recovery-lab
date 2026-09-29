# Spec — P0.1: P0 Remediation

**Feature ID:** P0.1-remediation
**Status:** ready for implementation
**Owner:** Maciej Lasota
**Depends on:** P0 (all fifteen tasks implemented; review bundles present)
**Blocks:** acceptance of P0; therefore blocks P1

## 1. Purpose

Close three blocking defects and two lesser items found in the P0 acceptance review, so that the two claims P0 exists
to support can actually be made:

1. **The out-of-band isolation claim.** The experiment claims that the evidence store is architecturally unreachable
   from the victim. That must be true of the code as written, not merely of the code as currently configured.
2. **The acceptance claim.** The experiment claims that the substrate was verified. That requires knowing which
   criteria were mechanically verified and which were attested, and requires the load-bearing ones to be mechanical.

P0.1 adds no new capability. It removes a hatch, makes a latent failure fail early and loudly, upgrades verification,
proves one untested guard, and pins the environment for reproducibility.

## 2. Problem statement

### F-1 — the boundary component contains a read hatch

`bin/lab-wal-receive` is the forced SSH command for the guest `postgres` principal and is the entire outward channel
from victim to host. It contains a branch of the form: if `SSH_ORIGINAL_COMMAND` equals a magic probe string **and** a
sentinel file exists beside the script, then `cat` a file under `EVIDENCE_ROOT` and exit 0.

Three distinct problems, in increasing order of importance:

- **Unverified.** No acceptance criterion asserts the sentinel is absent, so the hatch can be left enabled while the
  suite reports green. That is precisely the failure class this project studies.
- **Wrong mechanism.** The hatch exists to let the isolation suite's regression phase go red. It achieves that by
  creating a genuine read path *through the boundary being tested*. AC-13 therefore validates "the check can fail"
  using a deliberate weakness in the component under test, which is circular.
- **Unsound.** Anyone who reads this script sees a conditional victim-to-evidence read path. The
  isolation claim does not survive that reading, whatever the sentinel's state.

### F-2 — a latent evidence-stream failure passes acceptance

At P0 close the `wal2json` slot showed `active=false` with `retained_bytes` ≈ 436 MB against a 64 MiB warning
threshold and an 8 GB `max_slot_wal_keep_size`. AC-10 asserts only that retention is *bounded*, so it passed. But with
no consumer attached, retention grows monotonically; on reaching the cap the slot is invalidated and the logical
decoding stream — the sole source of database change evidence — stops. That would occur partway through an
experimental matrix, after hours of runs, and the loss would not be obvious.

### F-3 — nine of eighteen criteria are self-attestation

`bin/lab-verify` resolves nine criteria through a helper equivalent to
`return token in text and "FAIL" not in text`, where `text` is a markdown file written by the implementing agent.
This has two consequences. It conflates verification with self-report under a single "18/18 PASS" headline, and it is
brittle in an absurd direction: an honest observation containing the word FAIL turns a criterion red. Two of the nine
are load-bearing for research claims and must become mechanical: before-image presence (without it, "damaged data
retained" is unmeasurable) and heartbeat density (the LSN-to-time index that makes a coordinate resolvable).

### F-4 — an untested safety guard

`bin/lab-reset` is documented to refuse a rollback of `DS_PGDATA` while PostgreSQL is running. The T012 test intended
to prove this was skipped because guest `/tmp` is `noexec` and the test binary would not execute. Given that the same
task discovered a genuine and subtle defect — `zfs rollback -r` on a parent does not restore descendant dataset
contents, requiring deepest-first child rollback — the untested guard in that same component warrants proving.

### F-5 — hygiene

`${PG_DATA}.pre-zfs` remains on the guest: a stale copy of a PostgreSQL data directory, capable of confusing a later
restore path or a human. Separately, the exact OS and PostgreSQL versions are recorded only in prose, not in a
machine-readable artefact that the environment table can be generated from.

## 3. Scope

### In scope

- Removal of every test-only widening path from `bin/lab-wal-receive`, and re-implementation of the isolation
  regression phase by host-side mutation instead.
- A command-surface enumeration test for the WAL append channel.
- A persistent logical-decoding consumer, with slot lag failing closed rather than warning.
- Tier labelling of all eighteen P0 criteria in `bin/lab-verify`, per-tier totals, and mechanical re-implementation of
  the two load-bearing attested criteria.
- A `noexec`-safe live-process test for the reset guard.
- Removal of the stale data directory; pinning of OS and PostgreSQL versions into `etc/lab.env`.
- Re-run of the full acceptance suite and update of the P0 checklist and limitations.

### Out of scope

- Any change to `specs/P0-lab-substrate/contracts/` — the coordinate triple, `lab.env` and CLI contracts stay frozen.
- Mechanical re-implementation of the seven non-load-bearing attested criteria. They stay tier A, labelled honestly.
- Any P1 work: ground-truth oracle, results row schema, analytics, representations, model harness.
- Restructuring or rewriting components beyond the named repairs.

## 4. Requirements

### FR-1 Boundary integrity
FR-1.1 `bin/lab-wal-receive` MUST contain no code path, reachable by any input, environment variable, sentinel file or
argument, that reads, lists or emits the content of anything under `EVIDENCE_ROOT`, `RESULTS_ROOT`, or any archive
directory other than the append target.
FR-1.2 The only operation the channel accepts MUST be an append of a named WAL segment to the current incident's
archive directory, and it MUST continue to refuse overwrite of an existing segment.
FR-1.3 A command-surface enumeration test MUST present a fixed corpus of at least twelve candidate invocations —
including the removed probe string, path traversal attempts, shell metacharacter injection, alternate verbs and an
empty command — and MUST assert that only the intended append class succeeds.
FR-1.4 No file matching `.t009-regression-*` or any equivalent sentinel may exist anywhere under the deploy root, and
an acceptance criterion MUST assert their absence.

### FR-2 Isolation regression by external mutation
FR-2.1 The isolation suite's red phase MUST be produced by mutating state outside the component under test. Permitted
mechanisms: changing host-side ownership or mode on a scratch path under `EVIDENCE_ROOT`; adding a temporary,
clearly-named SSH authorised-key entry without a forced command. Prohibited: any flag, variable or file that the
component under test reads.
FR-2.2 The suite MUST still demonstrate three phases — PASS, then FAIL, then PASS — and MUST exit non-zero if the
middle phase does not fail.
FR-2.3 The mutation MUST be reverted in the same invocation, and reversion MUST be asserted, including destruction of
any temporary key material.
FR-2.4 A passing assertion MUST continue to distinguish permission-denied from file-not-found; the latter is an ERROR,
never a PASS.

### FR-3 Evidence stream continuity
FR-3.1 A persistent consumer of the `wal2json` slot MUST run for the lifetime of an incident, writing decoded change
records to the host-side evidence store as newline-delimited JSON.
FR-3.2 The consumer MUST be supervised such that it restarts on failure and its absence is detectable; it MUST record
its last confirmed flush position.
FR-3.3 Slot lag MUST fail closed: `bin/lab-slot --check` MUST exit non-zero when retained WAL exceeds the warning
threshold, when the slot is inactive while an incident is open, or when the slot is invalidated.
FR-3.4 Steady-state retained WAL, with the consumer running, MUST sit below the warning threshold; the observed
steady-state value MUST be recorded.
FR-3.5 Consumer liveness MUST be a precondition of opening an incident, and MUST be asserted by the full acceptance
suite.

### FR-4 Verification tiers
FR-4.1 Every one of the eighteen P0 criteria MUST carry a tier, M or A, in `bin/lab-verify` output.
FR-4.2 `bin/lab-verify` MUST print per-tier totals and MUST NOT print a single undifferentiated total as its headline.
FR-4.3 No criterion may be satisfied by matching a token in prose. Tier A criteria MUST assert on a machine-readable
field in a committed artefact.
FR-4.4 AC-6 (before-images on UPDATE and DELETE) and AC-14 (heartbeat density and LSN monotonicity) MUST be
re-implemented as tier M, re-derived at verification time.
FR-4.5 `bin/lab-verify` MUST emit machine-readable JSON in addition to human output, with one object per criterion
carrying id, tier, requirement reference, command, expected, observed and result.

### FR-5 Reset guard proof
FR-5.1 The refusal of `bin/lab-reset --tier t1` to roll back `DS_PGDATA` while PostgreSQL is live MUST be proven by
test, using a mechanism that does not require executing a file from a `noexec` mount.
FR-5.2 The test MUST assert the refusal is by design — non-zero exit, message naming the precondition — and MUST
assert that no snapshot rollback occurred, by comparing dataset state before and after.
FR-5.3 The complementary positive case MUST also be asserted: with PostgreSQL stopped, the same rollback succeeds.

### FR-6 Environment pinning and cleanup
FR-6.1 `${PG_DATA}.pre-zfs` MUST be removed, after asserting the live data directory is on `DS_PGDATA` and the
cluster is healthy.
FR-6.2 `etc/lab.env` MUST record exact versions: guest OS release, kernel, ZFS module and userland, PostgreSQL server
version and `wal2json` version, plus host OS release and kernel.
FR-6.3 A reproducible environment table MUST be emitted at `docs/environment.md`, generated from
`etc/lab.env`, not hand-written.

## 5. Acceptance criteria

| ID | Criterion | Tier | Discharges |
| --- | --- | --- | --- |
| RC-1 | `bin/lab-wal-receive` contains no branch referencing a probe string, sentinel file or debug flag; verified by pattern scan and by reading the file | M | FR-1.1 |
| RC-2 | No file matching `.t009-regression-*` or equivalent exists under the deploy root | M | FR-1.4 |
| RC-3 | Command-surface enumeration: ≥12 candidate invocations, exactly the append class succeeds, all others non-zero | M | FR-1.3 |
| RC-4 | Legitimate append still works; overwrite of an existing segment still refused | M | FR-1.2 |
| RC-5 | `bin/lab-isolation-test --regression` shows PASS/FAIL/PASS with the red phase caused by host-side mutation, and exits 0 | M | FR-2.1, FR-2.2 |
| RC-6 | Post-regression state is byte-identical to pre-regression state; temporary key material destroyed | M | FR-2.3 |
| RC-7 | A file-not-found probe is reported as ERROR, not PASS | M | FR-2.4 |
| RC-8 | Consumer is running, supervised, and restarts within 30 s of a kill | M | FR-3.1, FR-3.2 |
| RC-9 | Decoded JSONL is being written and grows under load; last flush position recorded | M | FR-3.1 |
| RC-10 | `bin/lab-slot --check` exits non-zero on each of: over-threshold retention, inactive slot with an open incident, invalidated slot | M | FR-3.3 |
| RC-11 | Steady-state retained WAL below warning threshold with consumer running; value recorded in `lab.env` | M | FR-3.4 |
| RC-12 | Opening an incident fails when the consumer is down | M | FR-3.5 |
| RC-13 | All 18 P0 criteria carry a tier; per-tier totals printed; no single undifferentiated headline | M | FR-4.1, FR-4.2 |
| RC-14 | No criterion resolves by token-in-prose; the prose-matching helper is gone from `bin/lab-verify` | M | FR-4.3 |
| RC-15 | AC-6 re-derived live: `UPDATE` and `DELETE` on a scenario relation yield old-tuple values in the decoded stream | M | FR-4.4 |
| RC-16 | AC-14 re-derived live: heartbeat interval within tolerance over a sampled window, LSNs strictly monotonic | M | FR-4.4 |
| RC-17 | `bin/lab-verify --json` emits one object per criterion with all required fields | M | FR-4.5 |
| RC-18 | Reset guard refuses with PostgreSQL live, no rollback occurs, and succeeds with PostgreSQL stopped | M | FR-5 |
| RC-19 | `${PG_DATA}.pre-zfs` absent; cluster healthy on `DS_PGDATA` | M | FR-6.1 |
| RC-20 | Versions pinned in `lab.env`; `docs/environment.md` generated from it | M | FR-6.2, FR-6.3 |
| RC-21 | Full suite re-run green after all repairs, with tier totals, and the P0 checklist updated | M | all |

## 6. Traceability

| Finding | Serves research integrity of | Rationale |
| --- | --- | --- |
| F-1 | The out-of-band isolation claim (ADR-002, ADR-003) | an isolation claim that fails inspection undermines every result that depends on it |
| F-2 | Continuity of database change evidence for SC-01 through SC-04 | a slot that dies mid-matrix destroys the sample |
| F-3 | Every claim P0 supports | self-attested criteria are not independent evidence |
| F-4 | Reset correctness, on which ablation validity depends | recovery can only be adjudicated against a correct reset |
| F-5 | Reproducibility and the environment table | the method must be reproducible from recorded versions |
