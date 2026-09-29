# ADR-P10-6 — How SC-01 is padded: natural-size anchor, WAL-tail placement, driver-checkpoint bookkeeping

Status: accepted 2026-09-24 (P10 Q001, before any scaling data)
Authority: Article XX.1 (resolve by precedence), Article XV (amend by supersession).
Amendment: `sdd/specs/P10-token-scaling/contracts/scale-generator.amendment-1.md` A1–A3.

## Context

The frozen generator contract asks for four things at once:

- **C1.1** a fixed true recovery point, with real records unchanged;
- **C1.2** legitimate padding interleaved across the timeline;
- **C4** placement that depends on `(seed, target)` only, never the injection log or oracle;
- **C2** a 10 000-token anchor.

Measured against the frozen incident, these are not all satisfiable as written.

1. **The anchor.** SC-01's natural R0 prompt is 19 435 canonical tokens. Padding only
   adds, so 10 000 cannot be reached. C2's own rationale is "the anchor near SC-01's
   natural ~17.9k".
2. **The optimum.** The oracle's optimum is the largest legitimate manifest `commit_lsn`
   strictly below the injection's. Any onset-blind rule that lets padded commits land
   anywhere can drop one between the optimum and the injection and move it (breaking
   C1.1). A rule that avoids that interval has to know where it is, which violates C4 and
   leaves a padding-free hole beside the onset that a model could read as a leak.
3. **Physical room.** Within a WAL segment, consecutive real records are 48–160 bytes
   apart, and one real concurrency inversion leaves no room at all. With real LSNs fixed,
   the maximum uniform density of uniquely-numbered padded changes is effectively zero.
   `lab-ledger-verify` also requires commit LSNs to be unique, in range and monotone in
   commit order. The only physical room is the unused tail of each 16 MiB segment:
   11 slots, 8.73 s of the 40 s grid, spread across windows 3–19.

## Decision

- **Anchor.** The 10 000 target is the unpadded natural incident, and its measured size
  is recorded.
- **Placement.** Padding goes only in WAL-tail slots, chosen by a seeded stream that sees
  only `(seed, n, slots)`. Each padded transaction is one INSERT or UPDATE on `p2_probe`,
  rendered exactly as wal2json would render it, at realistic record spacing.
- **Bookkeeping.** Padded commits are recorded at the workload driver's next existing
  manifest checkpoint, the same coarse rule the driver applies to its own commits. The
  real cycle at 09:16:46.46 physically committed before the injection yet is recorded at
  the injection LSN, so this is the incident's native semantics, not an invention. No new
  commit_lsn value appears below the injection, so the optimum is invariant **by
  construction**. It is also re-checked on every emitted incident, and a failure refuses
  emission.
- **Oracle comparison.** Invariance is checked with the pure `lab_oracle.select_optimum`
  rule. The live `lab-coordinate` heartbeat lookup has drifted since P1: it returns a
  2026-08-26 wall clock for the frozen optimum LSN, so a live comparison would differ even
  with zero padding. The frozen coordinate is carried forward only when the optimum LSN
  and selected record are proven identical.

Padding is therefore onset-blind in placement and faithful to the capture's physics and
the driver's bookkeeping. Every existing ledger check passes without special-casing it.

**How far "onset-blind" goes (following the Q001 independent review).** *Where* padding
goes, and what each padded record contains, never depends on the onset. *How much*
padding there is (the count n) is calibrated so that the frozen R0 view reaches the
target. That view's top-3 ranking uses the frozen P3 baseline, which is declared from the
injection start. P9's prompts had the same property.

The dependence is disclosed, not engineered away: changing P3 would break the anchor's
byte-identity with P9. A decoy-onset control measures it. Moving the onset P3 reads from
`1/E1000168` to `1/E3000638` leaves placement byte-identical for a fixed n, and shifts the
calibrated n by 2.0% (5 629 → 5 740 at 200k).

## Consequences

- **Bursts, not a flat rate.** Padding arrives as dense legitimate traffic after WAL
  segment switches, not uniformly in time. The switches are already visible to a model in
  the real LSNs, so this adds no onset information.
- **Identifiable padding.** Padded xids sit above the real range, because real xids are
  consecutive and fixed, and padded row ids are all new (≥ 88 000 704). A model could in
  principle notice this and set the padding aside. The scaled confounder is therefore an
  upper bound on difficulty only in so far as models do not exploit that cue. This is
  stated as a limitation of synthetic padding. It is a synthetic-origin cue, not an onset
  leak.
- **Only the draws are nested.** For a smaller count, the placement draws are a prefix of
  those for a larger one. The materialised records (xids, keys, update targets, values,
  LSNs) are assigned in time order, so they differ between targets.
- **Visible windows can change.** The frozen P3 anomaly rule reorders the lower two of the
  three visible windows as padding grows. Recorded per scale, not intervened on.
  Window 15, which holds the damage, stays first.
- **Controls pass.** The zero-padding build reproduces P9's R0, R1 and R2 prompts
  byte-for-byte (`a6c05004…`, `aaa23618…`, `7f38a906…`). A 40 000-event build reconciles
  exactly and passes `lab-ledger-verify`.
