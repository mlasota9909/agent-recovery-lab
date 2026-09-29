# FROZEN CONTRACT AMENDMENT 1 — Arm B Protocol (answerable task framing + resolvable-locator grammar)

**Amends:** `arm-b-protocol` (frozen by H001)
**Supersedes:** clause R4 (extraction grammar) and the task framing of §2 of `arm-b-protocol.md`
**Frozen by:** J003
**Status:** FROZEN — changes only by further amendment-through-supersession (Article XV).
**Authority:** Article XVII (subject sees only `model_view`, never the answer), Article VIII (refusal never coerced),
Article I (deterministic harness), Article II (provenance-blind), Article XV (amend by supersession).

## 1. Why this amendment exists

Under the P6 grammar, SC-01 Arm B returned zero determinations and a 100% refusal rate across R0/R1/R2 × K
(`logs/review/H009/headline.json`). J001's diagnosis (see `logs/review/J001/refusal-diagnosis.json` and ADR-P6.1-1)
established the proximate causes from the verbatim completions:

- a **rigid answer grammar** — P6 required exactly `COORDINATE: window=<int> lsn=<postgres-lsn-text>`, a two-field line
  in a single (hex) LSN form — which the extractor treated as a refusal whenever the model answered in any other shape;
  and
- a **vocabulary mismatch** — R1's content presents integer LSNs and R2's presents integer ranges, neither of which is
  the hex LSN the prompt demanded, so the model could not name the requested form from R1/R2 at all.

This amendment makes the task **answerable from each representation's own vocabulary** without touching the frozen
representations and without loosening the guard. The original `arm-b-protocol.md` stays byte-identical; this file
supersedes only its §2 framing and R4 grammar.

## 2. Redefined task framing (supersedes §2)

The model is asked, for the SC-01 incident and the recovery probe `PB-6-candidate-windows`, to identify the **recovery
coordinate**: the latest safe point before the damaging activity began. It is told to name that point using **whichever
locator the evidence provides** — a window index, a PostgreSQL LSN (in whatever form it appears), or a timestamp — and
that it may answer `REFUSAL` **only** when the evidence genuinely does not let it localise a safe point. It is given
only the `model_view` (six keys, no answer). Refusal remains legitimate and uncoerced; it is simply no longer the
artefact of an answer format the evidence cannot satisfy.

## 3. Redefined extraction grammar (supersedes R4)

The model ends its answer with exactly one machine-parsable tagged line, in one of:

- `COORDINATE: <locator> [<locator> ...]` — a determination, carrying **at least one** locator token:
  - `window=<int>` — a window index; resolved to the last-safe LSN of that window via `bin/lab-coordinate`, exactly as
    Arm A resolves a candidate window;
  - `lsn=<postgres-lsn>` — an LSN in **either** canonical hex (`X/Y`) **or** integer form; normalised to integer
    `(high<<32)+low` (hex) or taken as-is (integer);
  - `ts=<iso8601>` — a timestamp; resolved to the nearest safe LSN at or before it via `bin/lab-coordinate`.
- `REFUSAL: <free-text reason>` — a declared inability to localise a safe point.

Resolution rules:

- If multiple locators are present and resolve consistently (same coordinate within the incident's skew tolerance), the
  determination stands. If they resolve inconsistently, the outcome is a **refusal** (ambiguous), never a guessed pick.
- If a `COORDINATE` line carries no parsable locator, or a locator that `bin/lab-coordinate` cannot resolve or that is
  out of the incident's range, the outcome is a **refusal** (unresolvable), never a guess.
- If both a `COORDINATE` and a `REFUSAL` line appear, or neither, the outcome is a **refusal**.

All LSN comparison and resolution is integer `(high<<32)+low`; no string LSN comparison.

## 4. What is unchanged and still binds

- **R1 — identical prompt except content.** The system prompt, task instructions, answer-format instructions and
  refusal instructions are byte-identical across R0/R1/R2; only `model_view.content` differs. (Re-proven on the amended
  template by H003-style diff, AC-P6.1-09.)
- **R2 — single guarded assembly path.** `bin/lab-arm-b-prompt` remains the only assembler and still calls
  `bin/lab-modelview-guard` on the `model_view` before templating. The broadened grammar admits **no**
  `answer`/`reference`/`candidates` structure; the guard still refuses any input carrying the reference answer
  (Article XVII). A locator the model *chooses* is not the pre-computed answer.
- **R5 — refusal is first-class and never coerced.** Preserved exactly: an empty/ambiguous/unresolvable locator, both
  tags, or neither, all record `outcome="refusal"` with `lsn_int=null`; no heuristic or "best guess" coordinate is
  substituted; no re-prompt to "try again" is issued (Article VIII).
- **R6 — verbatim, provenance-scrubbed rationale.** Unchanged.
- **R7 — harness determinism.** Given a fixed completion, assembly, extraction and scoring are pure functions yielding a
  byte-identical coordinate and score. Unchanged.
- **R8 — replicates.** Each representation is run `K` times; all completions retained; per-representation outcome and
  replicate agreement computed from the K records. Unchanged.

## 5. Broadened is not loosened

The grammar now accepts more *forms of a locator the model must still choose correctly*; it does not accept a
pre-computed answer, and scoring is unchanged (the P4 restore+validate path against the same oracle). Picking the wrong
window, LSN or timestamp scores as damage retained or legitimate work lost, exactly as before. The guard and the
refusal path are unchanged. This is a correction that makes the task answerable, not a relaxation that admits the
answer key.

## 6. Change control

Frozen at J003 and hash-recorded in `logs/review/J003/`. Further change supersedes via `arm-b-protocol.amendment-2.md`
with its own ADR. This file stays byte-identical (Article XV).
