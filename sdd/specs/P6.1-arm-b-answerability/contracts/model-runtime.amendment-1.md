# FROZEN CONTRACT AMENDMENT 1 — Model Runtime containment (correction to the true cross-host topology)

**Amends:** `model-runtime` (frozen by H001)
**Supersedes:** clause R2 ("offline only", loopback) of `model-runtime.md`, and the semantics of `offline_verified`
**Frozen by:** J002
**Status:** FROZEN — changes only by further amendment-through-supersession (Article XV).
**Authority:** Article X (lab containment), Article XV (amend by supersession), Article XIII (verification tiers),
Article XVIII (a claim must be checkable against reality, not assumed).

## 1. Why this amendment exists

`model-runtime.md` R2 requires the runtime to be loopback-bound with no outbound network connection, and H002 recorded
`offline_verified:true`. The real deployment is **cross-host**: the model is served by vLLM on host `gb10a:8000` and
reached through a LiteLLM proxy on `c220m3:4001`; the harness endpoint is `http://c220m3:4001`. A cross-host call is not
loopback-only, so the original check asserted a property the deployment does not have. This is a private-lab
arrangement and is acceptable; the contract and its check must state and verify **what actually holds**, not a
loopback fiction. The original `model-runtime.md` stays byte-identical; this file supersedes only its containment
clause and the meaning of `offline_verified`.

## 2. Recorded topology (the truth of record)

| Element | Value |
| --- | --- |
| Harness endpoint | `http://c220m3:4001` (LiteLLM) |
| Backend | vLLM on `gb10a:8000` |
| Model alias used | the pinned local alias `gb10a-deepseek-v4-flash` (H001 `weights_sha256`) |
| Cloud alias present but NOT used | `deepseek-v4-pro` (must never be the target) |
| Network | private lab network only |

## 3. Redefined containment property (supersedes R2)

- **R2a — private-network endpoint.** The endpoint host resolves to a private / lab address (RFC-1918, link-local, or a
  known lab host recorded in `etc/lab.env`), never a public or cloud address.
- **R2b — no public egress during an invocation.** While a `bin/lab-model` invocation is in flight, no connection to a
  public (non-private) IP is observed from the invoking host. Egress is *tested*, not assumed.
- **R2c — pinned local alias only.** The request targets the pinned local alias; the cloud alias `deepseek-v4-pro` is
  never targeted.
- **R2d — fixed weights.** The weights hash reported/loaded for the alias equals the H001-pinned `weights_sha256`.

`containment_verified` is set true only when R2a–R2d all hold for the observed invocation, and the passing sub-checks
are recorded. This is stronger than the original clause: the original *assumed* no egress by asserting loopback; this
*tests* egress directly.

## 4. `offline_verified` — redefined semantics

`offline_verified` now means "R2a–R2d verified for this invocation" (private-network, no public egress, pinned local
alias, fixed weights). It no longer means "loopback socket". Records written under the original meaning are superseded;
J004's re-run records carry the new meaning.

## 5. Record additions (echoed per run, alongside the H001 `model-runtime.json` fields)

| Field | Type | Meaning |
| --- | --- | --- |
| `endpoint_host` | string | the resolved endpoint host (e.g. `c220m3`) |
| `endpoint_is_private` | boolean | R2a result |
| `public_egress_observed` | boolean | R2b: true is a violation |
| `alias_targeted` | string | the alias actually requested; must be the pinned local alias |
| `cloud_alias_targeted` | boolean | R2c: true is a violation |
| `weights_hash_matches_pin` | boolean | R2d result |
| `containment_verified` | boolean | R2a ∧ R2b ∧ R2c ∧ R2d |

## 6. What is unchanged

R1 (one model, declared by identity + weights hash), R3 (no fine-tuning), R4 (pinned greedy decoding), R5 (verbatim I/O
capture) and R6 (the model sees only `model_view` bytes from the single choke point) are unchanged and still bind. Only
the containment clause R2 and the meaning of `offline_verified` are superseded here.

## 7. Change control

Frozen at J002 and hash-recorded in `logs/review/J002/`. Further change supersedes via `model-runtime.amendment-2.md`
with its own ADR. This file stays byte-identical (Article XV).
