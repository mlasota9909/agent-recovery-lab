# SDD Package, Tranche P6.1 (Arm B Answerability: diagnose the null, correct containment, make the task answerable)

Same format as P0..P6: **GitHub Spec Kit** layout, extended with a `work-instructions/` tier below `tasks.md` that
Spec Kit itself does not provide.

Unpack so it **merges into** the existing `<repo>/sdd`. Nothing under any prior `specs/*/` directory is
edited, and no frozen contract file is mutated. This tranche repairs two defects found in the P6 acceptance review and
closes the class behind the more serious one with a new constitutional article.

## Why this tranche exists

P6 built the Arm B harness cleanly: one pinned local model, a single guarded choke point (`bin/lab-arm-b-prompt` →
`bin/lab-modelview-guard`), refusals recorded as first-class data, real runtime tokens kept distinct from the P5
estimate. `bin/lab-verify-p6` closed 19/19. The mechanics are sound. But the review found two problems the gate could
not have caught, because the gate was built to verify mechanics and to record refusals honestly — not to assert the
experiment produced signal.

**D1 — the headline is a total null, and a null was reported without being root-caused.** Across R0/R1/R2 × 5
replicates, the model returned **zero determinations and a 100% refusal rate** (`logs/review/H009/headline.json`:
R0 `determinations:0, refusal_rate:1.0`; R1 and R2 the same). There is therefore no R0-vs-R1-vs-R2 comparison — the
number the whole experiment turns on does not yet exist. Critically, the context window is 262,144 tokens and R0 consumed
only 17,893, so this is **not** a context-overflow story; R0 carried canonical hex LSNs, fit comfortably, and still
refused every replicate. A 100% refusal across all three arms points at the instrument (the prompt and the answer
grammar), not at the representations — but that must be *proven by reading the completions*, not assumed. A null result
that passes a green gate is not a finding until its root cause is established and the instrument is ruled out.

**D2 — the containment check verifies a property the deployment does not have.** The frozen `model-runtime` contract
(R2) requires the runtime to be *loopback-bound* with *no outbound network connection*, and `offline_verified` was
recorded true. But the real topology is cross-host: LiteLLM on `c220m3:4001` fronting vLLM on `gb10a:8000`. A cross-host
call cannot be loopback-only, so the check passed by measuring something narrower than the contract states. The
topology itself is a legitimate private-lab arrangement; the *contract and its check* must be corrected to assert what
actually holds (private-lab network only, no public-internet egress, no cloud alias, fixed local weights), or the
"contained/offline" claim rests on a check that does not measure the real path.

## What P6.1 delivers

| # | Deliverable | Closes |
| --- | --- | --- |
| 1 | New **Article XVIII** — a null or degenerate result must be root-caused and the instrument ruled out before it is reported as a finding | The null-reported-through-a-green-gate class |
| 2 | **J001** diagnosis: every H009 completion classified to a proximate refusal cause from the verbatim bytes; ADR-P6.1-1..4 | D1 root cause of record |
| 3 | **`model-runtime.amendment-1.md`** (Article XV supersession): records the real cross-host topology and redefines the containment property to what holds; `bin/lab-model` containment check rewritten to verify it, with a negative test | D2 |
| 4 | **`arm-b-protocol.amendment-1.md`**: broadens the answer grammar to a resolvable locator (window / LSN hex-or-int / timestamp) and relaxes the task framing so it is answerable from every representation's own vocabulary — byte-identical across R0/R1/R2, refusal still first-class, guard still enforced | D1 fix |
| 5 | **J004** re-run of SC-01 Arm B across R0/R1/R2 × K, honest headline, prior null quarantined as superseded; **J005** gate + criterion mapping + memo | D1 result |

## Target environment

Unchanged and confirmed by the P0..P6 builds:

- Host `r740core`, Ubuntu 26.04 LTS, KVM, ext4 root. Agent has `sudo`.
- Victim guest `thesisvm01`, keyless SSH from host, agent has `sudo` inside.
- PostgreSQL 18.4, wal2json 2.6-3, ZFS 2.4.1-1ubuntu5, devices `/dev/vdb` + `/dev/vdc` guest-side.
- Arm B model (pinned in H001): `gb10a-deepseek-v4-flash`, quant `exl3-k2`, 262,144-token context, greedy decoding,
  reached via LiteLLM `http://c220m3:4001` fronting vLLM on `gb10a:8000`. The cloud alias `deepseek-v4-pro` is not used.
- Deploy root `<repo>`. Config `etc/lab.env`.
- Gates today: `bin/lab-verify` 18/18, `-p1` 24/24, `-p1.1` 16/16, `-p2` 18/18, `-p2.1` 16/16, `-p3` 19/19, `-p3.1`
  16/16, `-p4` 19/19, `-p5` 19/19 (after P5.1), `-p5.1` 16/16, `-p6` 19/19.
- Constitution: seventeen articles in force (Article XVII = subject-visible surface excludes the answer); J001 adds the
  eighteenth.

## Install

```bash
# on r740core, as mlasota
cd <repo>
ls sdd/specs/P6.1-arm-b-answerability/tasks.md   # sanity check
```

## Execute

One task per invocation, in order, dry run first. **Do not batch.**

```bash
cd <repo>

<executor> --print "$(cat sdd/prompts/execute-P6.1.md)

TASK_TO_EXECUTE: J001
MODE: DRY_RUN"

<executor> --force "$(cat sdd/prompts/execute-P6.1.md)

TASK_TO_EXECUTE: J001
MODE: EXECUTE"
```

Order: `J001 -> J002 -> J003 -> J004 -> J005`. `J005` is the gate and runs last.

## What you review after each task

Open `sdd/specs/P6.1-arm-b-answerability/work-instructions/WI-Jnnn.md`, read its *Review bundle* and *Operator review
checklist*, then check `<repo>/logs/review/Jnnn/` exists and its `acceptance.md` rows are tier-labelled
per Article XIII. Tick the row in `checklist.md` yourself — the agent does not own the `Reviewed` column.

The task to read line by line is **J001**, because its diagnosis decides whether the null is an instrument artefact you
fix (D1) or a genuine finding about the model that you report. If the diagnosis is wrong, J003 fixes the wrong thing and
J004 produces another meaningless number.

## Anti-goals

Do not, in P6.1: change any frozen contract file (supersede by amendment instead); rebuild or re-fit the R0/R1/R2
representation artefacts (they are sound — their P5/P5.1 hashes must re-verify); enrich R1/R2 content or shrink R0 to
manufacture a result (the representations are frozen; only the shared prompt and grammar change); install or swap the
model, fine-tune, or add an adapter (Article I / model-runtime R3); coerce a refusal into a guess or re-prompt to "try
again" (Article VIII / arm-b-protocol R5); let the answer grammar broaden into reading the reference answer (Article
XVII — the guard still binds); read `principal` in any path (Article II); make a gate pass by weakening what it checks.
If a task appears to require one of these, it has been misread.
