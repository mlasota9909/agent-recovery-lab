# P11 — Operator Checklist

- [x] **R001** grammar + plan digests recorded and timestamped BEFORE any re-score row. Read the grammar yourself and confirm it is a rule, not "accept whatever is near the answer".
- [x] **R002** extractor rebuilt twice → byte-identical parses. Answer-blind negative test passed (parse identical with and without the oracle key in scope).
- [x] **R003** all 161 retained completion records re-parsed, including 155 current submitted units. All 52 unchanged positions with an old score retained that verdict. Two previously unscored historical attempts are listed separately under ADR-P11-2. No new `incorrect_corrupt`.
- [x] **R004** either fired on the mechanical trigger (contained, seed 42, same prompts, flagged rows) OR recorded skip-by-rule. Confirm no infeasible cell was ever re-run.
- [x] **R005** analysis refused each tampered original/amendment digest (Article XXI). H4 is NULL, H1-R is NULL and H3-R HOLDS. No degradation was detected at the tested endpoints; equivalence is not claimed (frozen analysis amendment 1).
- [x] **R006** reserved (outside repository scope).
- [ ] **R007 — unmet prior-gate requirement.** The new gate and close-out record are implemented. All 12,134 prior files/links are unchanged. P11 reports **M 11/12, A 1/1, total 12/13**. AC-P11-13 remains unmet because unchanged P10 reproduces its pre-existing P0 regression failure (**31/32**). See `logs/review/R007/close-out-memo.md` and `remaining-requirement.json`. No waiver is claimed.
- [ ] **Operator review:** review the actual finding: the pooled small-scale claim was not supported and is withdrawn; no within-window degradation was detected at the tested endpoints; P10's feasibility finding is unchanged. This checkbox requires the operator's review, not the executor's attestation.
