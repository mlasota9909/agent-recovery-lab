# FROZEN CONTRACT — Model Runtime (the offline local model used as Arm B)

**Contract ID:** model-runtime
**Frozen by:** H001
**Status:** FROZEN — changes only by amendment-through-supersession (Article XV).
**Produced/observed by:** `bin/lab-model` (H002); consumed by `bin/lab-arm-b` (H005).
**Authority:** Article V (stock mechanisms), Article X (lab containment), Article I (determinism as far as the runtime
allows), Article XIV (provenance of record).

## 1. Purpose

Fix, declare and pin the one model used in the entire project. Arm B's result is only interpretable if the model, its
weights and its decoding are known and held constant while the representation varies. This contract records what the
model is and constrains how it may be invoked, so that a difference in Arm B's success across R0/R1/R2 is attributable
to the representation and not to a changed model, changed weights, or changed sampling.

## 2. Hard rules

- **R1 — one model, declared by identity and weights hash.** Exactly one model is used for all Arm B runs across
  R0/R1/R2 and all replicates. Its `model_id`, `quantization` and `weights_sha256` are recorded here. Changing any of
  them requires a superseding amendment and re-running every Arm B result.
- **R2 — offline only (Article X).** The runtime is bound to a loopback address and makes **no outbound network
  connection**. Every `bin/lab-model` invocation is checked for outbound sockets; an outbound connection is a
  containment violation and the run is rejected.
- **R3 — no fine-tuning, no training.** The model is used as distributed. No LoRA, no adapter, no gradient step, no
  retrieval-augmented weight change. The representation does the work, not a tuned model. (If, and only if, base
  performance is inadequate and an adapter is later justified, that is a superseding amendment with its own ADR — never
  a silent change.)
- **R4 — pinned decoding.** Greedy decoding: `temperature=0`, `top_p=1`, `top_k` disabled, a fixed integer `seed`, and
  a fixed `max_tokens`. Recorded here and echoed into every run record. No sampling.
- **R5 — verbatim I/O capture.** Every invocation records, verbatim: the exact bytes sent (the assembled prompt), the
  exact completion returned, the real `prompt_tokens` and `completion_tokens` reported by the runtime, and the
  wall-clock `latency_ms`. These are the raw evidence; nothing is paraphrased.
- **R6 — the model never sees anything but `model_view` bytes.** `bin/lab-model` accepts only the assembled prompt from
  the single choke point (`bin/lab-arm-b-prompt`, H003), which is built from a guarded `model_view`. `bin/lab-model`
  does not read the ledger, the reference answer, the injection log or the oracle.

## 3. Record schema (`model-runtime.json`, one object; also echoed per run)

| Field | Type | Meaning |
| --- | --- | --- |
| `model_id` | string | the model's published identifier (family + size + revision) |
| `quantization` | string | e.g. `q4_K_M`, `q8_0`, `fp16` — the exact weights variant loaded |
| `weights_sha256` | string | SHA-256 of the weights file(s) actually loaded |
| `runtime` | string | the local inference runtime + version (loopback-bound) |
| `endpoint` | string | the loopback endpoint (e.g. `http://127.0.0.1:<port>`) — must be a loopback address |
| `decoding` | object | `{temperature:0, top_p:1, top_k:0, seed:<int>, max_tokens:<int>}` |
| `offline_verified` | boolean | set true only when an invocation was observed to open no outbound socket |
| `context_window` | integer | the model's context length in tokens (bounds how much `content` fits) |

## 4. Example (illustrative, non-normative — the real values are discovered and recorded in H001)

```json
{
  "model_id": "qwen3-27b-instruct",
  "quantization": "q4_K_M",
  "weights_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "runtime": "llama.cpp-b1234 (loopback)",
  "endpoint": "http://127.0.0.1:8081",
  "decoding": {"temperature": 0, "top_p": 1, "top_k": 0, "seed": 42, "max_tokens": 512},
  "offline_verified": true,
  "context_window": 32768
}
```

## 5. Change control

Frozen at H001 and hash-recorded in `logs/review/H001/`. Any change to model, weights, quantisation or decoding
supersedes via `model-runtime.amendment-N.md` with its own ADR, and invalidates every Arm B result produced under the
prior pinning (they must be re-run). This file stays byte-identical (Article XV).
