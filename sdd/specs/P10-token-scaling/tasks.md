# P10 — Tasks

| ID | Title | Produces | Key ACs |
|---|---|---|---|
| Q001 | Freeze contracts + pre-register + size the sweep | both contracts frozen w/ digests; Article XXI record; sizing note; K decision | 01 |
| Q002 | Build the deterministic scale generator | `bin/lab-scale-generate`; padded ledgers per target | 02, 03, 07 |
| Q003 | Verify scale integrity + representation parity | reconciliation report; parity report; oracle-invariance report | 03, 04, 05 |
| Q004 | Run the scaling sweep | `results/scaling-runs.jsonl` | 06, 07 |
| Q005 | Pre-registered scaling analysis | two-curve figure; H1/H2/H3 eval; verbatim interpretation | 08, 09, 10, 11 |
| Q006 | Reserved (outside repository scope) | — | 09, 10 |
| Q007 | Gate + close-out handoff | `lab-verify-p10`; prior-manifest check; close-out memo | 12, 13 |

One task per invocation. Q002/Q003 independent after Q001; Q005 after Q004; Q006 after Q005; Q007 last.
