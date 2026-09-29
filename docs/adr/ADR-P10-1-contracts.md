# ADR-P10-1 — P10 contracts frozen; padding is legitimate-only and onset-blind in placement

Status: accepted 2026-09-24 (P10 Q001)
Authority: Article VII (frozen contracts), Article XV (amend by supersession), Article XXI (pre-registration).

## Decision (from `sdd/specs/P10-token-scaling/plan.md`)

The generator pads SC-01 with legitimate activity only. Its placement depends only on
`(seed, scale_target)` and never on the injection log or the oracle, so the true optimum
stays fixed and the onset cannot leak through placement.

As padding grows, the malicious window's relative position drifts. That position is
recorded per scale so the "lost in the middle" effect can be read against it.
`scale-generator.amendment-1.md` A2 and ADR-P10-6 give the construction and its limits:

- WAL-tail placement;
- driver-checkpoint bookkeeping;
- the padding count is calibrated on the frozen view.

## Frozen digests (SHA-256; pinned in `sdd/specs/P10-token-scaling/contracts/frozen-hashes.json`)

| file | SHA-256 |
| --- | --- |
| `scale-generator.md` (as delivered; byte-identical to `thesis-sdd-P10.zip`) | `7758fd3a74aa506252f1f6dd9be12cb6cad9d176d223fb8a0f5f5c9eae45790c` |
| `scale-generator.amendment-1.md` | `8dac6439f6b5fff2e4f0bfd461af72fdfc975d1ceda838bc0695258a13a7f9a7` |
| `scaling-analysis-plan.md` (as delivered; byte-identical to `thesis-sdd-P10.zip`) | `80e6ec7efd14241be0c6d5082417fc2d0a083534343ef86d8bf92bcc37b914e8` |
| `scaling-analysis-plan.amendment-1.md` | `c9f270c4172b2eb28af74b831b2e80e18bfc3cdc956e6cb6cd1504b74457c403` |

The pre-registered analysis-plan digest is SHA-256 over the plan and its amendment:
`b4ddd9c773b35c67546485a17113eaa89305f46a8839b4fe5c202d78fe655dd5`. It was frozen at
`2026-09-24T02:36:05.031594Z`, when no `results/scaling-runs*` file existed.

`bin/lab-prereg-check`, `bin/lab-p10-sweep`, `bin/lab-p10-stats` and `bin/lab-verify-p10`
refuse to run if this digest changes.

## Review before freezing

The amendments were reviewed read-only before this freeze. The review's three blockers
were fixed before the digests above were taken:

- H1 had been changed to an unconditional rate; it is restored to conditional accuracy;
- no multiple-comparison correction was named; Bonferroni is now declared;
- the extent of onset-blindness was overclaimed; the claim is narrowed and a decoy-onset
  control is added.

The four should-fixes were also fixed before the freeze:

- S\* is fixed by the preflight;
- the loss units are aligned with P4;
- the pre-registration timing check fails closed;
- the prefix claim is narrowed.

Details are in `logs/review/P10/decision-log.md`.
