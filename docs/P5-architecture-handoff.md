# P5 Representations R0 / R1 / R2 — Architecture Handoff (tranche close)

**Date:** 2026-08-25
**Status:** P5 **COMPLETE** — three representations and the identical query interface over the reconciled SC-01 ledger.
**Gate:** `bin/lab-verify-p5` (totals in `logs/review/F010/verify-p5.out`)
**Human review:** `sdd/specs/P5-representations/checklist.md` Reviewed column still ☐.

Load this file **together with** `docs/P4-architecture-handoff.md`. P6 builds the Arm B model harness that consumes `bin/lab-repr-query`. P7 drives R0/R1/R2 across the matrix. P5's anti-goals (do not invoke a model, do not fork the interface) are **P5's** — they are not P6's instruction.

```json
{
  "admissible": {
    "R0": true,
    "R1": true,
    "R2": true
  },
  "anti_goal_inversion": false,
  "artefacts": {
    "R0": "var/repr/SC-01_20260824T091611Z/R0/",
    "R1": "var/repr/SC-01_20260824T091611Z/R1/",
    "R2": "var/repr/SC-01_20260824T091611Z/R2/"
  },
  "article_count": 16,
  "blind_view": "views.analysis_view",
  "built_by_model": false,
  "event_count": 319,
  "harness_commit": "eed20b58e027c44a4465bbf58637a8017cc7bd59",
  "headline_db_jsonl_sha256": "bf21fff2c7c71b39a150d15c9d097c797006139497c51b5a865414433a1ac7dd",
  "headline_incident": "SC-01_20260824T091611Z",
  "lab_ready_blocked_by": "frozen_headline_d2",
  "next_tranche": {
    "P6": "builds the Arm B model harness that consumes bin/lab-repr-query",
    "P7": "drives R0/R1/R2 across the run matrix"
  },
  "p5": "builds representations R0/R1/R2 and the identical query interface",
  "p6": "builds Arm B model harness",
  "parity": true,
  "r0_vs_r2_pb4_evidence_bytes": 38475,
  "r0_vs_r2_pb4_ratio": 0.005145575839065005,
  "representations": [
    "R0",
    "R1",
    "R2"
  ],
  "tokenizer": "lab-ws-punct-1",
  "true_anomaly_window": 15
}
```

---

## 1. Where the build stands

```
P0    substrate ............. DONE
P0.1  remediation ........... DONE
P1    instruments ........... DONE
P1.1  provenance ............ DONE
P2    capture ............... DONE
P2.1  reconciliation ........ DONE
P3    analytics + Arm A ..... DONE
P3.1  gate integrity ........ DONE
P4    restore + validation .. DONE (walking-skeleton milestone)
P5    representations ....... THIS FILE
P6    Arm B model harness ... NEXT — modest local model over bin/lab-repr-query
P7    run matrix ............ NEXT AFTER P6
```

P5 built **no model**. Frozen contracts were **not** edited. SC-01 headline `db.jsonl` is byte-identical to the P4 close.

## 2. The three representations

All three are deterministic functions of the provenance-blind reconciled ledger (`views.analysis_view` / DuckDB `db_changes`). Event count is **319**.

| Rep | Artefact | content_hash |
| --- | --- | --- |
| R0 | `var/repr/SC-01_20260824T091611Z/R0/events.jsonl` | `25bff369c36784ae0ba8923f719036ca74b9ba560eddb672c3cba7fecfd64933` |
| R1 | `var/repr/SC-01_20260824T091611Z/R1/windows.jsonl` | `fbf77d349d539e698ef995f3ac602efb086e8a1b7191e951e21cc71b56dc8e88` |
| R2 | `var/repr/SC-01_20260824T091611Z/R2/graph.json` + `summaries.jsonl` | `0d0ebe449f0c57072ebf7229c926b7dee491c0fc15f3cc469e8b776dd6ec3c86` |

R2 summaries are rendered from fixed templates. `built_by_model=false` on every manifest.

## 3. Identical interface

`bin/lab-repr-query` answers the six frozen probes. Parity: only `content` and `telemetry` differ. Structural match: **True**.

## 4. SC-01 headline (R0-vs-R2)

True anomaly window **15**. All three representations point at it on PB-4 and PB-6. R2 evidence_bytes on PB-4 is **199** vs R0 **38674** (delta 38475, ratio 0.0051). Tokenizer `lab-ws-punct-1`.

## 5. What P6 must do

P6 builds the Arm B model harness. It points a modest local model at `bin/lab-repr-query`, records the coordinate as an `arm-coordinate` with `representation` in {R0,R1,R2}, and scores it through the unchanged P4 restore+validate path. Do not fork the interface.

## 6. Frozen-headline note

`bin/lab-ready` still exits 1 (`lab_ready_blocked_by=frozen_headline_d2`). Starting the consumer would mutate the 0444 ledger. Do not run live `bin/lab-verify` (P0) against the headline; use `bin/lab-regression`.
