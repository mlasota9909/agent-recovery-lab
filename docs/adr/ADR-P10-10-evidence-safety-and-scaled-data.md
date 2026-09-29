# ADR-P10-10 — Evidence safety when running frozen tools on padded copies; where scaled data lives

Status: accepted 2026-09-24 (P10 Q001)
Authority: Article XVI (read-only on evidence), Article III (evidence immutable), Article XX.1.

## Context

- Padded incidents must be processed by the unchanged P3/P5 pipeline, pointed at a copy
  of the evidence root.
- Four frozen wrappers (`bin/lab-analytics`, `bin/lab-anomaly`, `bin/lab-query`,
  `bin/lab-oracle`) re-source `etc/lab.env` without honouring an `EVIDENCE_ROOT`
  override. Called as commands, they would silently read and write the real SC-01
  evidence. `lab-oracle` would even replace its 0444 `oracle.json`.
- Padded incidents are large (tens of MB each at the upper targets). The public repository
  must not carry bulk data.

## Decision

- **In-process only.** P10 never invokes those four wrappers. It calls the same library
  functions in-process under a context that sets `EVIDENCE_ROOT` and `LAB_REPR_ROOT` to
  the padded copy.
- **Write guard.** A guard refuses any pipeline step whose resolved evidence dir or
  representation root is outside `incidents/scaled/`.
- **Baseline and comparison.** The prior-evidence manifest (668 strict files and the
  append-only restore cache) was captured at Q001 before anything was generated. It is
  compared after every task.
- **Scaled data location.** Padded incidents live under `incidents/scaled/` and are
  gitignored. They are regenerable bit-for-bit from `(seed, target)` (AC-P10-02), and
  their SHA-256 digests are committed in `runtime/p10-scaled-manifest.json`.

## Consequences

- The frozen wrappers stay byte-identical: no retrofit, no migration.
- Anyone with the repository and the frozen SC-01 evidence can regenerate every padded
  incident and verify it against the committed digests.
