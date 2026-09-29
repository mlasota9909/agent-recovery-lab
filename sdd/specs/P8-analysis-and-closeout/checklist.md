# P8 — Operator checklist (hand-checks)

- [ ] M001: open the analysis-input contract; confirm the active-partition query is defined
      and that a superseded row is explicitly excluded.
- [ ] M002: run the loader yourself; confirm 51 active from 116, partition {25,25,1}; then
      add `principal` to a comparison input and confirm the guard refuses.
- [ ] M003: regenerate the SC-01 actionability figure twice; confirm byte-identical, and that
      it shows R2 5/5, R0 1/5, R1 0/5.
- [ ] M004: read the compactness table; confirm SC-04 shows compactness_holds=false and R2>R0.
- [ ] M007: confirm dated backup and latest are byte-identical after the prefix rename.
- [ ] M008: read the close-out memo; confirm tier totals + validity partition + validated headline,
      and no undifferentiated pass total.
