# P6 architecture handoff

P6 runs Arm B: one pinned modest local model over SC-01 representations R0, R1 and R2,
scored through the unchanged P4 restore+validate path.

## Pinned model

- `model_id`: `gb10a-deepseek-v4-flash`
- `quantization`: `exl3-k2`
- `weights_sha256`: `c5da6dd1f48fc7eed95333921709c5139bb0c59a5a616417094088dd81a31187`
- `runtime`: litellm on c220m3:4001 -> vllm-spark on gb10a:8000
- `endpoint`: `http://c220m3:4001` (LiteLLM on c220m3; backend is vLLM on gb10a; no SSH tunnel)
- `decoding`: {"max_tokens": 512, "seed": 42, "temperature": 0, "top_k": 0, "top_p": 1}
- `context_window`: 262144

The cloud LiteLLM alias `deepseek-v4-pro` is not used.

## Guarded choke point

`bin/lab-arm-b-prompt` is the only assembler. It calls `bin/lab-repr-modelview` then
`bin/lab-modelview-guard` before interpolating `model_view.content` into the pinned
template. `bin/lab-arm-b` is the only Arm B caller of `bin/lab-model`.

## Refusal path

A `REFUSAL:` line, an absent or ambiguous tagged line, or an unparsable/out-of-range
coordinate is recorded as `outcome=refusal` with `arm_coordinate=null`. The harness
never substitutes a guess.

## Real tokens vs P5 estimate

P5 `token_estimate` remains the model-independent tokenizer figure. P6 lands the
runtime-reported `prompt_tokens` in results-row `token_count`. They are not conflated.

## SC-01 R0 vs R1 vs R2

See `logs/review/H009/headline.json`. Ground truth LSN is `1/E1000000`.

## P7

**P7 builds the run matrix** across SC-01..SC-04, reusing `bin/lab-arm-b` unchanged.
P6's anti-goals (do not install a second model, do not coerce refusals, do not bypass
the guard) stay in P6; they are not P7's instruction to skip Arm B.
