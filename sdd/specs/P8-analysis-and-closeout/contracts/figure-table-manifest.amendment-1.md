# FROZEN AMENDMENT 1 — figure/table manifest (P8)

Status: FROZEN on P8-M004 acceptance. ADR: `docs/adr/ADR-P8-2-sc01-compactness-ratio.md`.

## Superseded clause (verbatim)

> - FIG-5.3 | figure | compactness: evidence_bytes R0 vs R2 by scenario (log y), annotate SC-01 ~140x, SC-04 inversion
>           | `analysis/gen_fig.py fig53` | Y

## Replacement

FIG-5.3 continues to compare median `evidence_bytes` for R0 and R2 by scenario on a log y-axis and to annotate the
SC-04 inversion. Its SC-01 ratio MUST be calculated from the hash-pinned source at regeneration time and displayed as
40.1x when rounded to one decimal place (44,267 / 1,103), not transcribed as ~140x.
