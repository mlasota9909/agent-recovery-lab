# Governance and ADR index

## Constitutional articles

- Article I — Determinism in the measured path
- Article II — Provenance is for scoring, never for detection
- Article III — Evidence is out-of-band, append-only, immutable
- Article IV — CLI-first, text in, JSON out
- Article V — Stock mechanisms only; named prohibitions
- Article VI — Simplicity and anti-abstraction
- Article VII — Frozen contracts
- Article VIII — Fail loud
- Article IX — Traceability
- Article X — Lab containment and ethics
- Article XI — Evidence of work
- Article XII — No test hatches in boundary components
- Article XIII — Verification tiers
- Article XIV — Provenance of record
- Article XV — Amendment of frozen artefacts
- Article XVI — Read-only verification gates
- Article XVII — Subject-visible surface excludes the reference answer
- Article XVIII — Null results are root-caused before they are reported
- Article XIX — Independent units are isolated; completeness is not validity.
- Article XX — Bounded standing authority; resolve, record, continue
- Article XXI — Pre-registered analysis; report what it shows

## Architecture decision records

- [ADR-M001 — Redact internal-network IPs before public disclosure](adr/ADR-M001-privacy-redaction-public-repo.md)
- [ADR-M002 — Neutral wording in frozen contracts and one pinned report line](adr/ADR-M002-neutral-contract-wording.md)
- [ADR-P10-1 — P10 contracts frozen; padding is legitimate-only and onset-blind in placement](adr/ADR-P10-1-contracts.md)
- [ADR-P10-10 — Evidence safety when running frozen tools on padded copies; where scaled data lives](adr/ADR-P10-10-evidence-safety-and-scaled-data.md)
- [ADR-P10-2 — R0 and R2 are the contrast; R1 is not run in P10](adr/ADR-P10-2-r0-r2-contrast.md)
- [ADR-P10-3 — `infeasible_context` is a result, not a failure](adr/ADR-P10-3-infeasible-context-is-a-result.md)
- [ADR-P10-4 — Canonical tokens size the sweep; model tokens and real windows decide feasibility](adr/ADR-P10-4-canonical-tokens-size-the-sweep.md)
- [ADR-P10-5 — Report whatever it shows, under a pre-registered plan](adr/ADR-P10-5-report-whatever-it-shows.md)
- [ADR-P10-6 — How SC-01 is padded: natural-size anchor, WAL-tail placement, driver-checkpoint bookkeeping](adr/ADR-P10-6-padding-construction.md)
- [ADR-P10-7 — Verdicts on padded incidents: unchanged P4 for real rows, ledger replay for padded rows](adr/ADR-P10-7-verdicts-on-padded-incidents.md)
- [ADR-P10-8 — Per-model context windows and the `infeasible_context` rule](adr/ADR-P10-8-context-windows-and-feasibility.md)
- [ADR-P10-9 — Pre-registration made executable: H1 statistic, taxonomy, scope, K, recorded descriptives](adr/ADR-P10-9-preregistration-operationalisation.md)
- [ADR-P2.1-1 — Silent deviation from `capture-completeness.md` §4](adr/ADR-P2.1-1-capture-completeness-s4-deviation.md)
- [ADR-P2.1-2 — Recover xid from the wal2json transaction envelope](adr/ADR-P2.1-2-xid-envelope-recovery.md)
- [ADR-P3.1-1 — Gate-integrity defects D1 and D2 (not retro-justified)](adr/ADR-P3.1-1.md)
- [ADR-P3.1-2 — Regression runs against pinned fixtures, not the live headline](adr/ADR-P3.1-2.md)
- [ADR-P3.1-3 — Read-only is enforced by a before/after evidence manifest](adr/ADR-P3.1-3.md)
- [ADR-P5.1-1 — Answer key in the subject-visible envelope (D1, D2)](adr/ADR-P5.1-1-answer-key-in-subject-view.md)
- [ADR-P5.1-2 — Split `model_view` from `reference` by supersession](adr/ADR-P5.1-2-modelview-reference-split.md)
- [ADR-P5.1-3 — The split is enforced by a guard, not by documentation](adr/ADR-P5.1-3-modelview-guard.md)
- [ADR-P6.1-1 — Treat the P6 null as an instrument defect until diagnosed](adr/ADR-P6.1-1-null-is-instrument-defect.md)
- [ADR-P7.1-6: additive `live_heartbeat` value on the coordinate `resolved_by` enum](adr/ADR-P7.1-6-live-heartbeat-coordinate-enum.md)
- [ADR-P8-1 — Hash-pinned corrected SC-01 batch supplements the active matrix](adr/ADR-P8-1-sc01-corrected-batch-supplement.md)
- [ADR-P8-2 — Report the measured SC-01 compactness ratio](adr/ADR-P8-2-sc01-compactness-ratio.md)
- [ADR-P9-1 — Cross-model sweep rows land in a sidecar, not the frozen results schema](adr/ADR-P9-1-sweep-isolation.md)
- [ADR-P9-2 — The sweep targets the loopback LiteLLM gateway, not the offline c220m3:4001](adr/ADR-P9-2-loopback-gateway-endpoint.md)
- [ADR-P9-3 — Uniform `max_tokens` = 8192 for the cross-model sweep](adr/ADR-P9-3-decoding-budget.md)
- [ADR-P9-4 — H1's pre-registered primary test is the pooled Cochran's Q; the null is root-caused, not reframed](adr/ADR-P9-4-h1-pooled-primary-and-root-cause.md)
- [ADR-P9-5 — Reconcile etc/lab.env ZFS_VERSION to the VM's actual zfsutils string](adr/ADR-P9-5-labenv-zfs-userland-reconcile.md)
