# ADR-P9-2 — The sweep targets the loopback LiteLLM gateway, not the offline c220m3:4001

Status: accepted 2026-09-01 (P9 N001)
Authority: Article XX (resolve, record, continue), Article X + P6.1
`model-runtime.amendment-1.md` (containment R2a–R2d), Article XV (amend by
supersession, never silently deviate).

## Context

`model-runtime.amendment-1.md` records the P6.1 topology as harness endpoint
`http://c220m3:4001` (LiteLLM) forwarding to vLLM on `gb10a:8000`. WI-N002 repeats
`c220m3:4001 -> gb10a:8000`.

At P9 execution time `c220m3` is offline (Tailscale: "offline, last seen 2d ago");
`http://c220m3:4001` times out. A LiteLLM gateway on the lab host itself,
`http://127.0.0.1:4001`, is reachable and fronts the same private-lab vLLM
backends plus (unused) cloud aliases.

This is an internal contradiction between a work instruction and lab reality, with
a backward-compatible resolution — exactly the Article XX case for resolve-and-record.

## Decision

For P9 only, the sweep endpoint is `http://127.0.0.1:4001`. The three model
aliases route (verified via the gateway's `model/info` and each backend's
`/v1/models`) to private-lab backends:

| alias | backend | address class |
| --- | --- | --- |
| `gb10a-deepseek-v4-flash` | `203.0.113.20:8000` | RFC-1918 |
| `gympc-gemma4-26b` | `203.0.113.31:8090` | CGNAT 100.64/10 (lab tailnet) |
| `alienware-qwen38-27b` | `203.0.113.21:8010` | RFC-1918 |

The frozen `model-runtime.amendment-1.md` stays **byte-identical**. Its containment
property is preserved and, if anything, strengthened:

- **R2a private endpoint** — `127.0.0.1` is loopback, i.e. private. The original
  amendment already accepted a cross-host proxy as "private"; a loopback gateway
  is strictly more contained. Each per-alias backend address is also private.
- **R2b no public egress during invocation** — tested, not assumed: `lab-p9-model`
  reads `ss -tnp` for its own PID during the call; the only peer is
  `127.0.0.1:4001`. (Honest limit: the shared gateway process also fronts cloud
  aliases and does its own onward connection; isolation rests on never targeting
  a cloud alias plus the observed loopback-only egress of the invocation process,
  not on physical disconnection.)
- **R2c pinned local alias only** — `lab_p9.is_cloud_alias` refuses
  `deepseek-v4-pro`, `frontier-*`, `gemini-*`, `nemotron-*`, `glm-*`, `kimi-*`,
  `*-pro`, `arbiter`; the registry validator refuses any such alias in the set.
- **R2d fixed weights / digest** — the DeepSeek baseline keeps the H001 pinned
  `weights_sha256`; Gemma and Qwen record the backend's immutable model identity
  digest (served-id + HF root/revision + max_model_len), as
  `model-runtime.amendment-1.md` §5 and WI-N002 1a permit when raw weights are
  not reachable.

`bin/lab-model` and `lib/lab_model_runtime.py` are **unchanged** — they stay pinned
to `c220m3:4001` + the single DeepSeek alias for any P6.1 reproduction. P9 uses its
own path (`bin/lab-p9-model`).

## Consequences

- No frozen contract file changes; no digest moves.
- The P9 gate re-verifies R2a–R2d per model (N002) rather than assuming the P6.1
  result transfers (ADR-P9-5 in plan.md).
- If `c220m3` returns, P6.1 reproduction is unaffected; P9's recorded endpoint
  stays `127.0.0.1:4001` for provenance honesty.
