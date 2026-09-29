# P9 — CHECKLIST (update as tasks complete)

- [x] N001  contracts frozen + Article XXI + scope/model decision recorded + throughput
- [x] N002  3 models verified (distinct tokenizers, >=2 families, containment, hashes)
- [x] N003  interface parity across models + representation artefact hashes re-asserted
- [x] N004  sweep executed; completeness + validity partition recorded
- [x] N005  pre-registered analysis (plan-drift refusal proven); CIs/effect/Holm; interpretation
- [x] N006  Arm A vs Arm B head-to-head + interpretation-layer framing
- [x] N007  reserved (outside repository scope)
- [x] N008  gate + close-out memo; prior contract hashes re-verified

Hand-checks for the operator (do yourself):
- [x] Confirm the 3 model aliases are real, local, and differ in tokenizer/family.
      → gb10a-deepseek-v4-flash / gympc-gemma4-26b / alienware-qwen38-27b; backends
        203.0.113.20 / 203.0.113.31 / 203.0.113.21 (all private); 3 families,
        3 tokenizer fingerprints (35 / 58 / 57 tokens on a fixed probe).
- [x] Re-run one N005 analysis command; confirm byte-identical output + a CI is present.
      → `bin/lab-p9-stats` run twice: p9-statistics.{json,md} sha256 identical;
        H2 bootstrap 95% CIs present (DeepSeek [+0.20,+1.00], Gemma [-1.00,-0.40]).
- [x] Read the emitted interpretation; confirm it matches the observed outcome and
      carries NO universal language over n=1-scenario data.
      → branch not_H1 (pooled Cochran's Q p=0.236); verbatim plan-§4 text emitted;
        universal-language lint passes; Article XVIII root-cause section labelled
        Exploratory (not pre-registered).
