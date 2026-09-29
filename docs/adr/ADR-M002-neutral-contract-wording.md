# ADR-M002 — Neutral wording in frozen contracts and one pinned report line

Status: accepted 2026-09-25 (maintenance action before publishing the repository)
Authority: Article XX (resolve, record, continue), Article XV (amend a frozen artefact by
supersession, re-pin every derived hash in lockstep), following the ADR-M001 precedent.

## Context

The repository's scope is the experiment: its goals, method, code, evidence and results.
Seven frozen contracts carried incidental sentences about downstream reporting and external
review rather than about the experiment itself, and one line of the P9 statistics report
(emitted by `lib/lab_p9_stats.py`) did the same. Each contract digest is pinned in live
verification code; the P9 report and the contracts are also entries in P10's recorded
prior-evidence manifest.

## Decision

1. Only those sentences were reworded to neutral, experiment-focused text. No field, rule,
   schema, enum, threshold, parameter, example value or number changed in any file.
2. The P9 report line was reworded in `lib/lab_p9_stats.py` and the report regenerated with
   `bin/lab-p9-stats`. `p9-statistics.json` is byte-identical; `p9-statistics.md` differs in
   that one line only. The pre-declared interpretation, every statistic and the lint result
   are unchanged.
3. `lib/lab_redaction.py` records, per file, the digest before and after this change.
   Pinned constants in the gates are passed through `pinned()`; `lib/lab_verify_p1.py`
   passes the digest recorded in `logs/review/W002/contract-hashes.json` through it; and
   `lib/lab_p10.compare_manifest` reads each recorded prior-evidence entry for these files
   through `manifest_entry()`. Recorded review logs stay byte-identical: they were true when
   written, and the mapping here is the audit trail.
4. `repro/manifest.json` carries the two re-pinned P8 contract digests; the derived local
   reproducibility table was regenerated from it.

| file | digest before | digest after |
| --- | --- | --- |
| `sdd/specs/P1-ground-truth-harness/contracts/results-row.md` | `866edd5677645622669572dfb663a12137a9ca6f1e000f35e7766577b46b0cdf` | `9a8e2bbb7a4e62313a28f8e0d791e3eb210be9c1cef1d7d8e57ed594a2daf680` |
| `sdd/specs/P4-restore-validation/contracts/restore-report.md` | `974815821369d1e1477e65851cf0ba39e23e156adf63c5e3840baafa5b30d357` | `451ca3028497feaabcaafbc77a162130023ef60edf17c07718a4a9e64556d71d` |
| `sdd/specs/P6-arm-b-model-harness/contracts/arm-b-protocol.md` | `99368b81220490fdd5a0906d0ef398c2589749508563ed136f8a111f8b9bb31f` | `3c22626cec108bbfd8410b19cb8b369203e9f4d9f3160c34cd17c1cdc345f37b` |
| `sdd/specs/P7-scenario-matrix/contracts/run-matrix-plan.md` | `4665066de522a368126e580db94411a63de768008b2bf40f758a93fb73be840e` | `32a2c2572b1cd50ac89733c11959b9a08ea35521ce4a6506a5b4c99feadded30` |
| `sdd/specs/P7-scenario-matrix/contracts/scenario-definition.md` | `74a9c25f15b42ded29a59e3a24414a8bd9ec8f36bee4314bff768a951f78ef55` | `31d8c4a18aa4a9fc52cd2367781b31ac7ca9d03c77a6e7c7bdc6879c4c740855` |
| `sdd/specs/P8-analysis-and-closeout/contracts/analysis-input.amendment-1.md` | `85448cc6d46839791129b3a29fa4c00ab1bf999f2fc56c842669aac941562459` | `0f1e364d7643488558c554d1e5832783a7aabf821465257388f5fec3a8754fa5` |
| `sdd/specs/P8-analysis-and-closeout/contracts/figure-table-manifest.md` | `e9508ac05f0d66790753080448c14a41345e2328647e035753b3a317e0265361` | `1688c65422cdcfc8349a2419bb5efe0eebf0266aa2502bc0a847723a3624f3fd` |
| `analysis-out/analysis/p9-statistics.md` | `381f53ee570d1a64308f7bc57c3705e60473f83cd3678a4e7b5dd6ead3f77de3` | `93d8fb1edafbf5eeff6b7b6db9da47105aa8cca096bd8a6e7ec80796dc73b8ed` |

## Not affected

The P9 and P10 pre-registered analysis plans and their `frozen-hashes.json`, the P10
pre-registration digest, every results row, ledger, evidence file and scaled incident.

## Consequences

- Every gate's contract-hash check re-derives green against the redacted files, and
  `bin/lab-verify-p10` reports the same totals as before this change.
- A future edit to any of these files is still caught: `pinned()` maps only the exact
  recorded digest, and `manifest_entry()` only the exact recorded entry.
