# P8 architecture handoff — analysis and project close-out

Date: 2026-08-28
Status: P8 accepted; project build closed.

## Result of record

P8 is strictly downstream of the frozen experiment. It reads 116 physical matrix rows, derives the 51 active tails,
and aggregates only the validity partition of 25 determinations, 25 refusals, and one diagnosed run failure. The 99
supersession records remain attached as provenance and never enter an aggregate. Refusals remain observed outcomes.

The terminal gate reports Tier M 13/13 and Tier A 2/2. Its evidence-manifest read-only check passes. Historical
regression reports P0/P1/P1.1/P2/P2.1 at 5/5. P7 and P7.1 remain green at the amended schema digest
`103eaa92ea48bca7ebcc7ce451b1978d822e92af41dc92b8fbf8f1e7a26d3775`.

## Analysis architecture

- `analysis/active_partition.py` is the executable example query for the active-tail contract.
- `analysis/loader.py` is the sole analysis loader. It rejects fixtures, superseded injections, and identity fields in
  comparison views. Its comparison surface exposes only representation, bytes/tokens, refusal/outcome, verdict, and
  derived coordinate error.
- `analysis/gen_fig.py` and `analysis/gen_tab.py` are deterministic generators for FIG-5.1–5.4 and TAB-5.1–5.4.
  Every artefact carries source IDs, validity partition, and supersession provenance in a metadata sidecar.
- The lab lacks pandas/matplotlib and cannot create a venv without host package changes. Figures therefore use a
  deterministic standard-library PNG encoder with fixed dimensions, pixels, compression, and chunk ordering. Two-pass
  regeneration and terminal scratch regeneration prove byte identity.

## Autonomous architecture resolutions

### Corrected SC-01 source

The 51-row active matrix contains SC-02/03/04, while the accepted corrected SC-01 result lives in J004 because the
banked result ledger predates P6.1. ADR-P8-1 and `analysis-input.amendment-1.md` authorize only the three hash-pinned
J004 replicate batches as an SC-01 supplement. Matrix rules are unchanged; no result row was rewritten.

### Compactness scalar

The work package's estimated ~140x scalar cannot be regenerated from the accepted source. Median presented bytes are
44,267 for R0 and 1,103 for R2, a 40.133273x reduction. ADR-P8-2 and
`figure-table-manifest.amendment-1.md` replace only the stale scalar. SC-04 remains the explicit boundary: R2 is 1,088
bytes versus R0 at 799, so compactness does not hold there.

### Historical ADR indexing

Two older decisions cited by amendments existed in tranche plans/review evidence but lacked canonical files under
`docs/adr/`. P8 added index records for P2.1 xid-envelope recovery and P6.1 null-result diagnosis without changing the
frozen amendments. `docs/INDEX.md` now lists all twenty constitutional articles and all ADR files, with zero dangling
amendment references.

## Findings and limits

Actionability and compactness must remain separate. On P4-validated SC-01, R2 determines 5/5, R0 1/5, and R1 0/5.
SC-02 is also P4-validated. SC-03 and SC-04 remain set-validated supporting scenarios and must not be promoted. Several
determinations are safe but conservative (`incorrect_safe`): zero retained damage with legitimate work sacrificed,
supporting an operator-assist framing rather than autonomous production recovery.

The principal limitations are one pinned model, prompt sensitivity (P6 window 15 versus corrected J004 window 14),
shared historical SC-01 versus isolated SC-02/03/04, K=5 per representation cell, and the unchanged three-sigma
ranker threshold missing SC-02 Arm A at maximum z approximately 2.13.

## Reproduction and review entry points

1. `bin/lab-verify-p8`
2. `logs/review/M008/gate.json`
3. `logs/review/M008/hash_reverify.json`
4. `logs/review/M008/close-out-memo.md`
5. `logs/review/P8/decision-log.md`
6. `repro/manifest.json`
7. `docs/INDEX.md`
8. `sdd/specs/P8-analysis-and-closeout/checklist.md`

The tranche-neutral backup tool emits `backups/thesis-<UTC>.md` and updates `backups/repomix-latest.md`; the final
dated backup is produced after this handoff so it includes the handoff and complete review bundle.

## Consolidated terminal gate content

The machine-readable terminal gate is reproduced here as a concise criterion ledger. The full observations and source
objects remain in `logs/review/M008/gate.json`.

- `AC-P8-01` (Tier M): PASS — analysis-input contract and active query.
- `AC-P8-02` (Tier M): PASS — frozen figure/table manifest complete.
- `AC-P8-03` (Tier M): PASS — loader active partition.
- `AC-P8-04` (Tier M): PASS — comparison-view provenance and fixture guards.
- `AC-P8-05` (Tier M): PASS — all manifest artefacts regenerate byte-identically.
- `AC-P8-06` (Tier M): PASS — SC-01 actionability counts.
- `AC-P8-07` (Tier M): PASS — SC-01 compactness and SC-04 counter-result.
- `AC-P8-08` (Tier M): PASS — immutable scenario validation tiers.
- `AC-P8-09`, `AC-P8-10` (Tier A): reserved; outside the scope of this repository.
- `AC-P8-11` (Tier M): PASS — reproducibility manifest complete.
- `AC-P8-12` (Tier M): PASS — neutral byte-identical backup.
- `AC-P8-13` (Tier M): PASS — all frozen hashes unchanged.
- `AC-P8-14` (Tier M): PASS — twenty-article and complete ADR index.
- `AC-P8-15` (Tier M): PASS — tiered project close-out memo.

The schema-pin negative test substituted 64 zeroes for the expected digest and failed while naming
`etc/results-row.schema.json`. The production hash set was unchanged. `bin/lab-gate-readonly-check
bin/lab-verify-p8` passed with an identical evidence-tree manifest before and after execution.

## Consolidated reproducibility manifest

```json
{
  "analysis_contracts": {
    "analysis_input_amendment_1_sha256": "85448cc6d46839791129b3a29fa4c00ab1bf999f2fc56c842669aac941562459",
    "analysis_input_sha256": "379d4c6dfb18af07afbcf65018c2e3da4a1ac99dd3def8f81fb619ed3736507a",
    "figure_table_manifest_amendment_1_sha256": "54bcef8418f3aff040ca219da4455326706d1fbc571ffe1175a2b3db7ed0cc83",
    "figure_table_manifest_sha256": "e9508ac05f0d66790753080448c14a41345e2328647e035753b3a317e0265361"
  },
  "decoding": {
    "context": 262144,
    "max_tokens": 512,
    "replicates_per_cell": 5,
    "seed": 42
  },
  "environment": {
    "lab_env_path": "etc/lab.env",
    "lab_env_sha256": "cb774481254de0f7f7bb5f504e3d28c4210c81546f423a923ba30d0f6c67a663"
  },
  "model": {
    "endpoint_topology": "c220m3:4001->gb10a:8000",
    "id": "gb10a-deepseek-v4-flash",
    "quantisation": "exl3-k2",
    "runtime": "litellm-c220m3+vllm-spark-gb10a",
    "weights_sha256": "c5da6dd1f48fc7eed95333921709c5139bb0c59a5a616417094088dd81a31187"
  },
  "producer_commit": "6a07c0c6481dd09649e8b5ebf018e571bd77c9f4",
  "results": {
    "matrix_path": "results/matrix.jsonl",
    "matrix_sha256": "881d8290976da46a9220cb0bdbced4cfae6d6879fed5d6568301e5b1e5d66c7d",
    "schema_sha256": "103eaa92ea48bca7ebcc7ce451b1978d822e92af41dc92b8fbf8f1e7a26d3775"
  },
  "schema_version": 1,
  "versions": {
    "guest_kernel": "7.0.0-29-generic",
    "guest_os": "Ubuntu 26.04 LTS",
    "host_kernel": "7.0.0-29-generic",
    "host_os": "Ubuntu 26.04 LTS",
    "postgresql": "PostgreSQL 18.4 (Ubuntu 18.4-0ubuntu0.26.04.1)",
    "zfs": "2.4.1-1ubuntu5",
    "zfs_kmod": "2.4.1-1ubuntu5"
  }
}
```

## Consolidated governance index

All twenty constitutional articles are indexed: I–XI (base principles), XII (no boundary test hatches), XIII
(verification tiers), XIV (exact production provenance), XV (frozen amendments), XVI (read-only gates), XVII
(answer-key separation), XVIII (null-result diagnosis), XIX (isolated units and validity partition), and XX (bounded
authority to resolve, record, and continue).

The ADR index contains:

- ADR-P2.1-1 and ADR-P2.1-2 — capture-contract deviation and xid-envelope recovery.
- ADR-P3.1-1 through ADR-P3.1-3 — gate integrity, pinned-fixture regression, and manifest-enforced read-only checks.
- ADR-P5.1-1 through ADR-P5.1-3 — answer-key defect, model/reference split, and enforcement guard.
- ADR-P6.1-1 — null result treated as an instrument defect until diagnosed.
- ADR-P7.1-6 — additive `live_heartbeat` coordinate resolution.
- ADR-P8-1 — hash-pinned corrected SC-01 supplemental batch.
- ADR-P8-2 — measured SC-01 compactness ratio.

The cross-check reports 20 articles, 12 ADR files, and zero dangling amendment references.

## Final backup and delivery state

- Final Repomix archive: `backups/thesis-20260828T051657Z.md`
- Latest alias: `backups/repomix-latest.md`
- SHA-256: `00ff4105332713d600d8d3d8320dc3826ad57df01272ff4b53361ded48640896`
- Size: 7,159,921 bytes
- Repomix version: 1.18.0
- Packed files: 1,703
- Security scan: PASS; no suspicious files detected
- Dated archive/latest identity at production: PASS

## Additional handoff notes

- The final backup above predates this consolidation edit; after this handoff update, create a new final Repomix
  archive if the delivery snapshot must contain the consolidated document itself.
- The reproducibility manifest's `producer_commit` deliberately names the clean code state that produced it. It is not
  rewritten to later documentation-only commits, which would break exact production provenance.
- Reviewers should use generated sidecars and CSV files for numeric checking; PNGs are presentation surfaces.
- Do not aggregate all 116 physical rows. Only the 51 active tails are analysable.
- Do not convert refusals into missing data or imputed determinations.
- Do not describe SC-03/SC-04 as P4-validated, and do not restore the stale ~140x compactness claim.
