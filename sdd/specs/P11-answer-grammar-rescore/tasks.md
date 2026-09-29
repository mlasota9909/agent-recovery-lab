# P11 — Tasks

| ID | Title | Produces | Key ACs |
|---|---|---|---|
| R001 | Freeze grammar + plan, pre-register | both contracts frozen w/ digests; Article XXI record | 01 |
| R002 | Build the relaxed extractor | `bin/lab-regrammar`; determinism + answer-blind proofs | 02, 03, 04 |
| R003 | Re-parse + re-score the banked set | `results/rescoring-runs.jsonl`; consistency + safety reports; rerun-trigger.json | 05, 06 |
| R004 | (CONDITIONAL) confirmatory within-window re-run | top-up rows (or skip-by-rule record) | 11 |
| R005 | Pre-registered re-score analysis | H4/H1-R/H3-R eval; verbatim interpretation; figure | 07, 08, 09, 10 |
| R006 | Reserved (outside repository scope) | — | 10 |
| R007 | Gate + close-out handoff | `lab-verify-p11`; read-only proof; close-out memo | 12, 13 |

One task per invocation. R004 fires only if R003's trigger says so; R005 after R003 (and R004 if it fired); R006 after R005; R007 last.
