# Plan — P6.1: Arm B Answerability

## Architecture decisions (locked)

### ADR-P6.1-1 — the null is a defect of the instrument until proven otherwise, and it is diagnosed from primary evidence

`bin/lab-verify-p6` closed 19/19 and the P6 mechanics are sound: one pinned model, a single guarded choke point,
refusals recorded honestly, real tokens kept distinct from the P5 estimate. But `logs/review/H009/headline.json` shows
`determinations:0, refusal_rate:1.0` for all of R0, R1 and R2. There is no ablation result. Three facts narrow the
cause:

- The context window is 262,144 tokens; R0 used 17,893 (~7%). **Not overflow.**
- R0's `content` carries canonical hex LSNs (`1/E…`) — the exact form the P6 prompt asked for — and still refused every
  replicate. So a representation-vocabulary mismatch alone cannot explain R0; the **shared prompt and answer-extraction
  grammar** are implicated across all three arms.
- R1's content presents `last_safe_lsn_int` (integer) and R2 presents integer ranges (`[12897001..12897850]`), neither
  of which is the hex LSN the prompt demanded — so R1/R2 additionally suffer a **vocabulary mismatch** on top of any
  shared grammar problem.

This ADR names the null a defect of the same lineage as prior review findings: a result was reported (through a green
gate) without its cause being established from primary evidence. J001 classifies every one of the 15 retained
completions to a proximate cause from a fixed taxonomy, from the verbatim bytes, before any fix is designed. If — and
only if — the diagnosis shows the model genuinely reasons that the evidence is insufficient *even from R2's clean
summary with a permissive grammar*, then a residual refusal is a real finding (a modest model is insufficient even with
a good representation) and is reported as such after J003/J004. The diagnosis decides which.

### ADR-P6.1-2 — correct the containment contract to the truth of the deployment, do not pretend it is loopback

`model-runtime` R2 requires loopback-only with no outbound connection, and `offline_verified` was recorded true, but
the real path is LiteLLM `c220m3:4001` → vLLM `gb10a:8000` — cross-host. The check therefore passed by asserting a
narrower property than the contract states. The topology is a legitimate private-lab arrangement, and "offline" in the
sense that matters for the experiment still holds: no public-internet egress, no vendor/cloud model, fixed local weights,
no telemetry. By Article XV the frozen `model-runtime.md` is not mutated; `model-runtime.amendment-1.md` records the
cross-host topology and redefines the containment property to what is *true and checkable*:

- the endpoint resolves to a private lab address (RFC-1918 / known lab host), never a public or cloud address;
- no connection to a public IP is observed during an invocation;
- the target is the pinned local alias, never the cloud alias `deepseek-v4-pro`;
- the loaded weights hash equals the H001-pinned `weights_sha256`.

The check is rewritten to verify each element and record `containment_verified` with the sub-checks that passed. This
is a *correction to the truth*, not a weakening: the old check claimed loopback (false) and now the check claims
private-network-no-egress (true and stronger, because it actually tests egress rather than assuming it away).

### ADR-P6.1-3 — broaden the answer grammar to a resolvable locator; fix the prompt, never the representations

The representations are frozen and sound (P5/P5.1). The null is not fixed by changing what R0/R1/R2 contain; it is fixed
in the **shared** prompt and extraction grammar, which is where an unconfounded fix belongs (arm-b-protocol R1 keeps the
prompt byte-identical across arms except `content`). Two changes, both by amendment:

- **Grammar.** P6 required exactly `COORDINATE: window=<int> lsn=<postgres-lsn-text>` — a rigid two-field line in one
  LSN form. The amendment accepts a **resolvable locator**: `COORDINATE:` carrying at least one of `window=<int>`,
  `lsn=<hex-or-int>`, `ts=<iso8601>`. `bin/lab-arm-b-extract` resolves whichever is present to the frozen coordinate via
  `bin/lab-coordinate` (window→last-safe-LSN exactly as Arm A resolves it; integer or hex LSN normalised to integer;
  timestamp→nearest safe LSN). This is fair and unconfounded: scoring is via the P4 restore+validate path against the
  same oracle regardless of how the coordinate was expressed, and picking the *right* locator is still the task. Every
  representation exposes at least one resolvable locator in its own content (R0: hex LSN + timestamp; R1: window +
  integer LSN; R2: window + LSN range), so no representation is disadvantaged by vocabulary.
- **Framing.** The task instruction is relaxed so it asks for "the latest safe point before the damaging activity,
  named by whichever locator the evidence provides (a window, an LSN, or a timestamp)", and states refusal is
  appropriate *only* when the evidence genuinely does not localise a safe point. The refusal option is preserved
  (Article VIII / R5) but is no longer the path of least resistance created by an over-rigid answer format.

**Broadened is not loosened.** The grammar still admits no `answer`/`reference`/`candidates` structure; the guard
(`bin/lab-modelview-guard`, Article XVII) still runs on every assembled input and still refuses a spliced answer. An
empty, ambiguous, or unresolvable locator remains a refusal — no guess is ever substituted.

### ADR-P6.1-4 — corrected, never weakened; the re-run invalidates the prior null

Every P6 criterion still exists and still asserts its property. Where a mechanism changes — the containment check
(loopback → private-network-no-egress) and the extraction grammar (rigid → resolvable locator) — the change is recorded
in a machine-readable old→new mapping and is a correction or strengthening, never a relaxation. The prior null headline
is retained as `headline.superseded.json` with a pointer to the J004 re-run; it is not deleted, because the fact that
the first instrument produced a null is itself part of the record (and, per Article XVIII, part of the methodology
story). J004's re-run is the result of record from here.

## Constitutional change

Article XVIII is appended by J001:

> **Article XVIII — Null results are root-caused before they are reported.** A null, empty, or degenerate experimental
> result (no signal, total refusal, all-zero, or a single-valued outcome) MUST NOT be reported as a finding about the
> subject until its proximate cause has been established from primary evidence (the raw outputs, not a summary) and the
> instrument — the harness, the prompt, the extraction grammar, the measurement path — has been ruled out as the cause
> or corrected. A green gate that verifies mechanics and honestly records the null does not discharge this obligation.
> Where the instrument is corrected, the result is re-derived; where the null survives a corrected instrument, it is a
> genuine finding and is reported as such, with the diagnosis that establishes it.

This sits alongside Article XII (no test hatches), XIII (verification tiers), XIV (provenance of record), XV (amendment
of frozen artefacts), XVI (read-only gates) and XVII (subject-visible surface excludes the answer) as the seventh
lesson learned from review, each closing a class rather than an instance.

## Task breakdown

| Task | Owns | Closes |
| --- | --- | --- |
| J001 | Article XVIII; per-completion refusal diagnosis; ADR-P6.1-1..4 | D1 root cause + governance of record |
| J002 | `model-runtime.amendment-1.md`; rewritten containment check + negative test | D2 |
| J003 | `arm-b-protocol.amendment-1.md`; rebuilt `bin/lab-arm-b-prompt` + `bin/lab-arm-b-extract`; guard/refusal/parity negative tests | D1 fix |
| J004 | SC-01 Arm B re-run R0/R1/R2 × K; honest `headline.json`; prior null quarantined; determinism + blindness preserved | D1 result |
| J005 | `bin/lab-verify-p6.1` gate; re-derived `bin/lab-verify-p6`; contract-hash re-verify; old→new mapping; memo | all |

## Sequencing

J001 first (diagnosis and principle before any change — the fix must target what the completions actually show). J002
is independent of J003 and could run in either order, but is placed second because it is small and unblocks a clean
re-run environment. J003 depends on J001 (it fixes the cause the diagnosis established). J004 depends on J002 and J003
(it re-runs on the corrected containment check and the amended grammar). J005 is the gate and runs last.

```
J001 -- J002 -- J003 -- J004 -- J005
           \-----------/
      (J002 and J003 independent; both precede J004)
```

## Risks

- **J003 "fixes" the wrong thing because J001 mis-diagnosed.** Mitigated by J001 being tier-M classification from the
  verbatim completion bytes with per-completion evidence, operator-spot-checked against two raw completions; J003's
  design in ADR-P6.1-3 addresses both the shared-grammar and the vocabulary-mismatch causes, which the three known
  facts already implicate.
- **The broadened grammar leaks the answer.** Mitigated by AC-P6.1-10/11: the guard still runs on every input and still
  refuses a spliced `answer`/`candidates`; the grammar admits only a locator the model must *choose*, never a
  pre-computed result.
- **A representation is accidentally changed while relaxing the prompt.** Mitigated by AC-P6.1-12 requiring
  F002/F003/F004 artefact hashes to re-verify byte-identical; the fix touches only the shared prompt template and the
  extractor, never `bin/lab-repr-*`.
- **The relaxed framing coerces determinations (turns genuine refusals into forced guesses).** Mitigated by AC-P6.1-08
  and the R5 preservation: an unresolvable/ambiguous/empty locator is still a refusal, no guess substituted; the framing
  explicitly retains refusal as appropriate when the evidence does not localise a safe point.
- **The containment redefinition is used to quietly weaken the claim.** Mitigated by AC-P6.1-06 (a public/cloud target
  must be *caught*, proving the check tests egress rather than assuming it) and AC-P6.1-17 (old→new mapping; the new
  property is stronger — it tests egress — not weaker).
- **The re-run still nulls.** Then Article XVIII is satisfied by the corrected instrument, and a surviving refusal is a
  genuine finding: report per-representation refusal with its diagnosed cause, and let the operator decide whether the
  modest model is simply insufficient for SC-01 even with R2. That is a real, if disappointing, result — not a
  gate failure.
