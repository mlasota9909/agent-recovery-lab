# ADR-P5.1-3 — The split is enforced by a guard, not by documentation

**Status:** accepted
**Date:** 2026-08-25
**Tranche:** P5.1
**Related:** ADR-P5.1-1, ADR-P5.1-2, Article XVII

## Decision

`bin/lab-modelview-guard <model_view.json>` inspects the subject-visible bytes and refuses (non-zero exit, first violation named) any object that carries:

1. An `answer` or `reference` key at any depth.
2. A structured coordinate-answer field presented as JSON object keys: `candidates`, `last_safe_lsn_int`, or `first_lsn_int`/`last_lsn_int` as object fields (not as text inside `content`).
3. A provenance token (`principal` / `usename` / `session_user` / UID) in any key or value.

Top-level keys must be exactly the six `model_view` keys.

## What the guard permits

LSN digits appearing **inside the `content` string** are allowed. That is the evidence the model reads in order to *derive* a coordinate. R0's model_view is a raw LSN-ordered event log; a guard that rejected digits in `content` would make R0 impossible and would be wrong.

The guard forbids the **structured pre-computed answer**, not the appearance of a number in the evidence text.

## Why this is Article XVII as tier M

A documentation-only split would fail the same way Articles XII/II/XIV failed until a gate forced them. The guard makes "the subject was not handed the answer" a mechanically re-derived property: any future emitter that regresses into including `answer` is caught. Negative tests inject `answer` and `principal` into an otherwise-clean model_view and assert the guard goes red, then green after revert.
