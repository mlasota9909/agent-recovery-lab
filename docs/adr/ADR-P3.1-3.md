# ADR-P3.1-3 — Read-only is enforced by a before/after evidence manifest

**Status:** accepted  
**Date:** 2026-08-24  
**Tranche:** P3.1  
**Related:** ADR-P3.1-1 (D1), Article XVI

## Decision

Rather than auditing each gate's source by eye, `bin/lab-gate-readonly-check <gate>`:

1. Builds a recursive SHA-256 manifest of the evidence root into `logs/review/` (not under evidence).
2. Runs the named gate, capturing its exit and output.
3. Rebuilds the manifest.
4. Asserts equality. On mismatch it names the first changed path and exits non-zero. On match it exits with the gate's own exit code.

This makes "read-only" a mechanically re-derived property (tier M). It will catch any future gate that regresses into writing evidence — closing the **class**, not just the two D010 instances.

A gate that legitimately needs a mutable copy writes it under `logs/review/<id>/scratch/`, which is outside the evidence root and therefore not in the manifest.

The harness itself writes only under `logs/review/`. Its own run against a known-good gate must leave the evidence manifest byte-identical, or the enforcer is itself a D1 defect.
