# Checklist — P5: Representations R0 / R1 / R2 & the Identical Query Interface

The agent fills `Date` and `Bundle` when a task completes. **The operator owns the `Reviewed` column** — the agent
never ticks it.

| Task | Title | Date | Bundle | Reviewed |
| --- | --- | --- | --- | --- |
| F001 | Freeze both P5 contracts; record entry gate | 2026-08-25 | logs/review/F001/ | [ ] |
| F002 | `bin/lab-repr-r0` flat chronological event log | 2026-08-25 | logs/review/F002/ | [ ] |
| F003 | `bin/lab-repr-r1` structured temporal aggregates | 2026-08-25 | logs/review/F003/ | [ ] |
| F004 | `bin/lab-repr-r2` deterministic graph + summaries | 2026-08-25 | logs/review/F004/ | [ ] |
| F005 | `bin/lab-repr-query` identical query interface | 2026-08-25 | logs/review/F005/ | [ ] |
| F006 | determinism + fidelity + provenance-blindness | 2026-08-25 | logs/review/F006/ | [ ] |
| F007 | identical-interface parity test | 2026-08-25 | logs/review/F007/ | [ ] |
| F008 | telemetry: evidence_bytes + token_estimate | 2026-08-25 | logs/review/F008/ | [ ] |
| F009 | SC-01 headline + R0-vs-R2 delta + discrimination | 2026-08-25 | logs/review/F009/ | [ ] |
| F010 | `bin/lab-verify-p5` gate; hashes re-verified; handoff | 2026-08-25 | logs/review/F010/ | [ ] |

## Operator review order

1. `RESULT` line, `DETERMINISTIC REBUILD` and `PROVENANCE-BLIND` lines of the agent's report.
2. `logs/review/<task>/acceptance.md` — **check the tier column**, not just PASS.
3. The negative-test evidence. Confirm the check went red, then green again after revert.
4. `observations.md` — deviations and out-of-scope findings.
5. Hand spot-check two artefacts. For **F007**, diff the response envelope across R0/R1/R2 yourself and confirm only
   `content` and `telemetry` differ. For **F004/F006**, rebuild R2 yourself and confirm it is byte-identical and that
   no model was invoked. For **F009**, confirm all three point at the true SC-01 anomaly window and that R2's
   `evidence_bytes` is far below R0's for the recovery probe.

## Acceptance criteria coverage

| AC | Tier | Owning task |
| --- | --- | --- |
| AC-P5-01 | M | F001 |
| AC-P5-02 | M | F002 |
| AC-P5-03 | M | F003 |
| AC-P5-04 | M | F004 |
| AC-P5-05 | M | F004 |
| AC-P5-06 | M | F005 |
| AC-P5-07 | M | F005 |
| AC-P5-08 | M | F006 |
| AC-P5-09 | M | F006 |
| AC-P5-10 | M | F006 |
| AC-P5-11 | M | F007 |
| AC-P5-12 | M | F008 |
| AC-P5-13 | M | F008 |
| AC-P5-14 | M | F009 |
| AC-P5-15 | M | F009 |
| AC-P5-16 | M | F006 |
| AC-P5-17 | M | F010 |
| AC-P5-18 | M | F010 |
| AC-P5-19 | A | F010 |

Eighteen of nineteen criteria are tier M. The single tier A criterion is the handoff record, which asserts on
machine-readable fields, per Article XIII.

## Tranche exit condition

P5 is accepted when `bin/lab-verify-p5` reports every criterion PASS with per-tier totals printed separately and is
itself proven read-only over the evidence root; both P5 contracts are frozen and hash-verified; R0/R1/R2 are built as
deterministic, complete, reconciling, provenance-blind functions of the SC-01 ledger with admissible fidelity
manifests; the query interface answers all six probes identically across the three with only `content`/`telemetry`
differing, proven by the parity test and byte-identical on re-run; telemetry records exact `evidence_bytes` and a
pinned-tokenizer `token_estimate` with R2 < R0 on the recovery-relevant probe; the headline shows all three point
faithfully at the true SC-01 anomaly window; the discrimination negative proves fidelity/blindness are enforced; all
prior gates, regression and contract hashes (through P4) are unchanged; and the P5 handoff is written without
anti-goal inversion.

## Note for P6 and P7

- **P6** (Arm B) points a modest local model at `bin/lab-repr-query` and records the coordinate it chooses as an
  `arm-coordinate` with `representation` set to `R0`/`R1`/`R2`, scored through the unchanged P4 restore+validate path.
  Do not fork the interface for Arm B; the whole point of P5 is that Arm B cannot tell the representations apart except
  by content.
- **The contribution measurement** — R0-vs-R2 evidence-bytes/tokens at fixed model and fixed scenario — is what P7
  reports across the run matrix. P5 establishes it on SC-01; P7 scales it.
