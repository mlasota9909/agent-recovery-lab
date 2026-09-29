# P6 acceptance memo

P6 is accepted only after P6.1. Two defects the P6 gate could not catch were remediated:

- **D1** — SC-01 Arm B was a total null (`determinations:0`, `refusal_rate:1.0` on R0/R1/R2). J001 classified the 15 completions from verbatim bytes. J003 broadened the locator grammar. J004 is the result of record. The prior null is retained as `headline.superseded.json`.
- **D2** — containment claimed loopback while the topology is LiteLLM on c220m3 fronting vLLM on gb10a. J002 redefines the check to R2a–R2d (private-lab endpoint, no public egress, no cloud alias, weights pin).

```json
{
  "D1": "total null without root cause; diagnosed in J001; instrument corrected in J003; re-run J004",
  "D2": "containment claimed loopback; corrected to R2a-d private-lab / no public egress / no cloud alias / weights pin",
  "defects": [
    "D1",
    "D2"
  ],
  "p6_accepted_only_after": "P6.1",
  "prior_null": "logs/review/H009/headline.superseded.json",
  "result_of_record": "logs/review/J004/headline.json"
}
```
