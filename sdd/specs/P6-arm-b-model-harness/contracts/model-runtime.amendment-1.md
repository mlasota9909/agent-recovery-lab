# AMENDMENT 1 — Model Runtime: LiteLLM on c220m3 is the invocation endpoint

**Contract ID:** model-runtime.amendment-1
**Amends:** `model-runtime.md` (frozen by H001; this file does not edit it)
**Frozen by:** H001
**Status:** FROZEN — Article XV supersession. The base contract stays byte-identical.
**Authority:** operator direction (P6 package omitted the lab's existing inference gateway);
Article V (stock mechanism already deployed); Article X (lab containment: no public API).

## 1. Why this amendment exists

`model-runtime.md` R2 requires the runtime to be bound to a **loopback** address with no
outbound socket during invocation. That assumed a local inference binary on `r740core`.
No such binary is the Arm B subject. The operator-directed runtime is the lab's existing
LiteLLM gateway on **c220m3**, which already fronts the gb10a DeepSeek V4 Flash server.
An SSH local-forward to synthesise loopback is not LiteLLM's role and is not used.

## 2. Rules that supersede R2 for this project (R2' )

- **R2'.1 — one sanctioned gateway.** `bin/lab-model` invokes only the pinned LiteLLM
  endpoint recorded in `model-runtime.json` (`MODEL_ENDPOINT`). Today that is
  `http://c220m3:4001`. Changing host or port is a further amendment and invalidates
  prior Arm B runs.
- **R2'.2 — no public API.** Cloud LiteLLM aliases (`deepseek-v4-pro`, Gemini, NVIDIA
  hosted models, etc.) are refused. The only allowed `model_id` is
  `gb10a-deepseek-v4-flash` (gb10a vLLM behind LiteLLM).
- **R2'.3 — containment check.** A per-invocation socket observation still runs. A
  connection to the pinned LiteLLM host:port is the sanctioned hop and is **not** a
  violation. Any other non-loopback peer is a containment violation and the run is
  rejected. `offline_verified=true` means "no unsanctioned outbound", not "no TCP".
- **R2'.4 — no tunnel, no second gateway.** `bin/lab-model` does not open an SSH
  tunnel, SOCKS proxy, or extra reverse-proxy. LiteLLM on c220m3 is the gateway.

## 3. Unchanged

R1 (one model, weights hash), R3 (no fine-tune), R4 (greedy+seed), R5 (verbatim I/O),
R6 (model never sees ledger/reference/oracle) remain as in the base contract.

## 4. Recorded pinning (discovered, not guessed)

| Field | Value |
| --- | --- |
| `model_id` | `gb10a-deepseek-v4-flash` |
| `served_model` | `deepseek-v4-flash-0731-exl3-k2` |
| `quantization` | `exl3-k2` |
| `endpoint` | `http://c220m3:4001` |
| `backend` (LiteLLM target, not called by lab-model) | gb10a `203.0.113.20:8000` |
