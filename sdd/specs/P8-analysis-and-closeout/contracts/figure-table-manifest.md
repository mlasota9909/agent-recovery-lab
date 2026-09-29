# FROZEN CONTRACT — figure/table manifest (P8)

Status: FROZEN on M001 acceptance. Every reported artefact appears here or it is not reported.

Each entry: id | kind | source query (against loader) | regen command | validity-partition required (Y).

## Figures
- FIG-5.1 | figure | actionability by representation, SC-01 (determination vs refusal counts per R0/R1/R2)
          | `analysis/gen_fig.py fig51` | Y
- FIG-5.2 | figure | refusal rate by representation across all validated+supporting scenarios
          | `analysis/gen_fig.py fig52` | Y
- FIG-5.3 | figure | compactness: evidence_bytes R0 vs R2 by scenario (log y), annotate SC-01 ~140x, SC-04 inversion
          | `analysis/gen_fig.py fig53` | Y
- FIG-5.4 | figure | coordinate error vs ground truth for determinations (SC-01, SC-02), by representation
          | `analysis/gen_fig.py fig54` | Y

## Tables
- TAB-5.1 | table | matrix summary: cells, determinations, refusals, run_failures per scenario x representation
          | `analysis/gen_tab.py tab51` | Y
- TAB-5.2 | table | per-scenario verdict + validation tier (SC-01/02 P4, SC-03/04 set)
          | `analysis/gen_tab.py tab52` | Y
- TAB-5.3 | table | R0/R1/R2 comparison: refusal rate, median evidence_bytes, median prompt_tokens, compactness_holds
          | `analysis/gen_tab.py tab53` | Y
- TAB-5.4 | table | reproducibility manifest (rendered) : model, weights sha256, seed, decoding, commit, versions
          | `analysis/gen_tab.py tab54` | Y

Rule: a manifest entry whose regen command does not reproduce the committed artefact byte-identically
is a hard failure (AC-P8-05).
