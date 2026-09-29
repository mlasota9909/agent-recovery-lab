# P1 Ground Truth Harness — Architecture Handoff (tranche close)

**Date:** 2026-08-20  
**Status:** P1 COMPLETE — `bin/lab-verify-p1` **TIER M: 23/23 · TIER A: 1/1 · TOTAL: 24/24**, exit 0  
**P0 verify:** `bin/lab-verify` **TIER M: 9/9 PASS · TIER A: 9/9 PASS · TOTAL: 18/18** (re-checked at W010)  
**P1.1 X006 (2026-08-21):** P1 was accepted only after P1.1. **P2 entry is `bin/lab-ready` exit 0**, not the “P2: may begin” line below. See `docs/P1.1-architecture-handoff.md`.  
**Human review:** `sdd/specs/P1-ground-truth-harness/checklist.md` Reviewed column still ☐ (operator owns ticks). Read W002 and W007 line by line.

This file **supersedes** the W001-era `docs/P1-architecture-handoff.md` (open-of-tranche). Load it together with `docs/P0.1-architecture-handoff.md` and `docs/P0-architecture-handoff.md`.

Primary sources: `sdd/specs/P1-ground-truth-harness/`, `docs/p1-acceptance-memo.md`, `docs/throughput.json`, `logs/review/W001/`…`W010/`.

---

## 1. Where the build stands

```
P0  substrate ............ VM, ZFS, Postgres+logical decoding, out-of-band evidence, coordinate, reset  [DONE]
P0.1 remediation ......... boundary hardened, consumer supervised, verification tiered                  [DONE]
P1  instruments .......... oracle, results contract, ledger integrity, two-phase harness, null run      [DONE]
P2  capture .............. db.jsonl, snapshots.json, fs_diff.tsv, fs_hashes.tsv, DuckDB views         [NEXT]
P3  analytics + Arm A .... burst density, anomaly scoring, candidates, ranker, naive comparator
P4  restore .............. real PITR into sandbox, row/byte/schema validation, promotion gate
P5  representations ...... R0 flat, R1 temporal, R2 graph+summaries, identical query interface
P6  Arm B ................ modest local model harness over the representations
```

P1 built **instruments only**. No analytics, ranking, representations, model, real restore, or SC-02/03/04 damage logic. Stubs implement the P3 and P4 call shapes so those tranches are substitutions, not rewrites.

---

## 2. What P1 delivered

| Piece | Path | Why it is load-bearing |
| --- | --- | --- |
| Results-row contract | `sdd/specs/P1-ground-truth-harness/contracts/results-row.md` + `etc/results-row.schema.json` | Every reported number is a field in this row |
| Ledger-integrity contract | `…/contracts/ledger-integrity.md` | Slot rewinds on T1/T2; host ledger does not |
| Writer / validator | `bin/lab-results` | Append-only JSONL; no coercion |
| Barrier | `bin/lab-barrier` | Bounded wait for `lab-slot --check`; never proceeds degraded |
| SC-01 workload | `bin/lab-workload` as `lab_app` | Legitimate commits + `workload-manifest.jsonl` |
| SC-01 injector | `bin/lab-inject` as `lab_agent` | Scripted DELETE; `injection.json` |
| Oracle | `bin/lab-oracle` | Last legitimate commit LSN **strictly <** inject LSN |
| Two-phase harness | `bin/lab-generate-incident`, `bin/lab-evaluate-arm` | One incident, many arms, byte-identical GT |
| Stubs | `bin/lab-analyse-stub`, `bin/lab-restore-stub` | P3/P4 interfaces; verdict `stub` only |
| Views | `lib/views.py`, `lib/provenance_fields.py` | `scoring` with provenance; `analysis` without |
| Throughput + plan | `bin/lab-throughput`, `docs/throughput.json`, `docs/sample-size-plan.md` | Replaces "as many as possible" |
| Gate | `bin/lab-verify-p1` | AC-P1-01..24, per-tier totals |

P1 CLIs live as `bin/lab-*` wrappers that `source etc/lab.env` and `exec python3 lib/lab_*.py`. Implementation is under `lib/`. Guest `/tmp` is `noexec`; the workload worker is `lib/lab_workload_worker.py`, copied to `/home/lab_app/`. Guest has **no psycopg** — inject uses `psql`.

---

## 3. Do not re-litigate

P0 D-1..D-10 and P0.1 ADR-P01-1..7 still hold. P1 ADR-P1-1..8 are locked in `sdd/specs/P1-ground-truth-harness/plan.md`.

| ID | Decision |
| --- | --- |
| ADR-P1-1 | Results row frozen before harness code. Later tranches may **append** nullable fields; never rename/retype/repurpose |
| ADR-P1-2 | `generate-incident` and `evaluate-arm` are separate; `incident_id` is the join key |
| ADR-P1-3 | Only the oracle may read provenance (`usename`, `session_user`, UID). Analysis path must not |
| ADR-P1-4 | `lab-ledger-verify`: no duplicate LSN inside an incident; all commit LSNs in `[open, close]` |
| ADR-P1-5 | Every harness reset is followed by `lab-barrier` |
| ADR-P1-6 | Cycle time re-measured post-reset-guard; 49.335 s is **not** used |
| ADR-P1-7 | Results are append-only JSONL under `RESULTS_ROOT` |
| ADR-P1-8 | P1 restore/consistency verdict is `stub`. No code path emits `restore_verdict: correct` |

Three P0 contracts and the two frozen P1 originals remain byte-identical. P7.1 adds `results-row.amendment-1.md`; the generated schema is pinned at its amended hash.

---

## 4. Current operating point (2026-08-20T21:25Z check)

| Fact | Value |
| --- | --- |
| `archive/current` | `SC-01_20260820T051544Z` |
| Registered `incident.json` | eight SC-01 incidents (see §8) |
| Throughput-evaluate incident | `SC-01_20260820T051544Z` / `i_20260820T051544Z_1b449f` |
| Snapshots on current | `open` `s_20260820T051545Z`, `pre_injection` `s_20260820T051611Z`, `post_capture` `s_20260820T051625Z` — none invalidated at this check |
| PostgreSQL | **up** |
| Consumer | **down** (`unit_state=inactive`, `healthy=false`) |
| Slot | `invalidation_reason=wal_removed`, `slot_active=false` — idle-host drift after W010, **not** a P1 logic defect |
| `HARNESS_COMMIT_AT_P1_OPEN` | `18f05606cfb9327510ba09604a007ebfe16830d5` |
| Git HEAD | same 40 hex at P1 close (no further harness commits required then) |

**P1.1 X001 (2026-08-21).** W001 recorded that each results row's `harness_commit` would be git HEAD at `lab-evaluate-arm` time. That matched the frozen contract, not the P1 code: `lib/lab_evaluate_arm.py` copied `HARNESS_COMMIT_AT_P1_OPEN` into every row. X002 binds the field to `git rev-parse HEAD` at row-production time and refuses a dirty working tree. Do not re-bind the field to the P1-open env key.

**Before the next generate or P0-style live capture:** stop PostgreSQL, `lab-reset --tier t2` (or `t1` if you need pre-damage state) so the slot is restored from the ZFS snapshot, start `lab-consumer` for the current incident, then `lab-barrier`. Do **not** recreate `lab_slot` in database `postgres`.

---

## 5. `etc/lab.env` keys added by P1

Meanings of P0 keys unchanged. New keys:

```
HARNESS_COMMIT_AT_P1_OPEN=18f05606cfb9327510ba09604a007ebfe16830d5
RESULTS_SCHEMA=/home/mlasota/thesis/etc/results-row.schema.json
RESULTS_FILE_MODE=0444
BARRIER_TIMEOUT_S=120
SC01_SEED_ROWS=50000
SC01_TPS=20
SC01_MIX=insert:60,update:30,delete:10
SC01_TPS_TOLERANCE=0.25
SC01_MIX_TOLERANCE=0.15
SC01_BASELINE_S=10
SC01_INJECT_ROWS=200
```

Do not hardcode these values in `bin/` wrappers (P0 AC-1). Comments in `bin/lab-inject` / `bin/lab-workload` must say `ROLE_AGENT` / `ROLE_APP`, not the literal `lab_agent` / `lab_app` strings.

---

## 6. Frozen hashes (cite these, do not re-hash by eye)

P1 (W002 / W010):

```
866edd5677645622669572dfb663a12137a9ca6f1e000f35e7766577b46b0cdf  results-row.md
15f5740bf4cac9d5fabeabe5b06f1b5656355b0a6a2ba2518218e24dc21d2313  ledger-integrity.md
103eaa92ea48bca7ebcc7ce451b1978d822e92af41dc92b8fbf8f1e7a26d3775  results-row.schema.json (P7.1 additive enum amendment; results-row.md remains byte-identical)
```

P0 (R007):

```
01f0dbc60d7ab5670b8d9b135ab3c8983b9bd00df67e966dd10c36bbc4e5d5d1  cli.md
2080ac9f270aac0f8da718675ac8cb742d009a268fdeb5d634fef03c437c2eef  coordinate.md
6285e55865b82d6a42f8b558a3020c2ede6db4b8e048c669278c199e003ce138  lab-env.md
```

---

## 7. New P1 CLIs

| CLI | Role | Idempotence |
| --- | --- | --- |
| `lab-p1-open` | W001 gate; already done | `changed: false` |
| `lab-results` | `append` / `validate` / `close` | validate/close-when-444: `changed: false`; append is append |
| `lab-ledger-verify` | duplicate LSN + range containment | `changed: false` |
| `lab-barrier` | poll `lab-slot --check` | `changed: false` when already healthy |
| `lab-workload` | seed / start / stop / status / pull / check-rate | start-while-running: `changed: false` |
| `lab-inject` | SC-01 DELETE as `lab_agent`; `--verify-timing` | refuses a quiet system |
| `lab-oracle` | GT coordinate + scoring manifest | re-run: `changed: false` |
| `lab-generate-incident` | seven-step freeze | **always new id** (W008-14) |
| `lab-evaluate-arm` | t2 reset → analyse-stub → restore-stub → append row | **always appends** (AC-P1-17) |
| `lab-analyse-stub` | last snapshot at or before close | `changed: false` |
| `lab-restore-stub` | verdict `stub` | `changed: false` |
| `lab-throughput` | `--phase generate\|evaluate --repeats n` | **appends** measurements; refuses `n<5` and `n=1` |
| `lab-verify-p1` | AC-P1-01..24 | no mutation of frozen evidence |

JSON on stdout, logs on stderr, exit 0/1/2/3. No `|| true` on checks.

`lab-evaluate-arm --incident` takes the **archive** id (`SC-01_20260820T051544Z`), not `i_…`. It retargets `archive/current` via atomic symlink replace.

---

## 8. Registered incidents and the null-run proof

Host-registered (`incident.json` mode 0444):

- `SC-01_20260820T043543Z` — first P1 incident (hand-finished then evaluated ×3). GT wall_clock still 2026-08-17 (heartbeat gap). **AC-P1-17 proof.**
- `SC-01_20260820T045603Z`, `…T045731Z` — first two CLI generates
- `SC-01_20260820T051041Z` … `…T051544Z` — W009 generate ×5; last is the t2 evaluate target

AC-P1-17 (three stub evaluates, no regeneration), incident `i_20260820T043543Z_680721`:

Canonical `ground_truth_coordinate` sha256  
`8cee28b1d3a18f33f169cdc987423b824eb6276a61123b54b0fec586b792ce58`

Many unregistered `SC-01_*` directories exist from failed generate attempts. Ignore any tree without `incident.json`.

---

## 9. Sequencing constraints that will break the matrix if ignored

These are the expensive lessons. P2/P3 inherit them.

1. **Generate, then evaluate every arm, then generate the next incident.** T1 rollback to `pre_injection` destroys later ZFS snapshots on the shared dataset. After a subsequent generate, prior incidents show `post_capture` `invalidated=true` and cannot be t2-evaluated. Host evidence (`incident.json`, `db.jsonl`, `oracle.json`) remains.

2. **No valid `pristine` snapshot exists** on the leftover P0 incident. Generate uses **t1** even for a "first" P1 incident.

3. **Barrier cannot run before `--new`.** After T1 the slot rewinds; `lab-incident --new` creates the new consumer unit. Order in code: stop PG → t1 → `--new` → stop consumer → truncate new `db.jsonl` → snapshot `open` → start consumer → barrier → heartbeat → workload.

4. **Snapshot LSN is recorded after the ZFS snap and `pg_switch_wal`.** wal2json commits can sit slightly below open or slightly above sampled close. Generate **windows** `db.jsonl` to `[open_coordinate.lsn, close_lsn]` after `--close`, then `lab-ledger-verify`. That is containment of the registered ledger, not invention of LSNs.

5. **Evaluate must not append catch-up records onto a frozen ledger.** After T2 the slot rewinds; a live consumer would duplicate LSNs already in `db.jsonl`. `lab-evaluate-arm` copies the ledger bytes, runs consumer+reset+barrier, **stops the consumer, restores the bytes**, then verifies. Do not "fix" this by writing into the frozen file.

6. **Heartbeat must run during the incident LSN range** or `wall_clock`/`skew_ms` resolve to an old heartbeat (the 2026-08-17 leftover on `043543Z`). CLI-generated incidents start heartbeat after barrier.

7. **Guest `/tmp` is `noexec`.** Worker lives in `/home/lab_app/`.

---

## 10. Measured cycle times (replace 49.335 s)

`docs/throughput.json`, `measured_post_reset_guard: true`:

| Phase | n | median_s | min_s | max_s | sd_s |
| --- | --- | --- | --- | --- | --- |
| generate-incident | 5 | 75.539 | 74.810 | 76.153 | 0.447 |
| evaluate-arm (t2) | 10 | 32.903 | 32.423 | 33.210 | 0.269 |

Reset dominates both (generate ~24 s, evaluate ~30 s). Analysis stub ~0.17 s.

Core sample-size **plan** (complete result on its own: SC-01 + SC-02, near-instant, R0/R1/R2). These figures are projections; `completed_arm_runs` is 0.

- `planned_incidents` = 10  
- `representations` = 3  
- `replicates` = 5  
- `planned_arm_runs` = 10 × 3 × 5 = **150**  
- `planned_hours` = **1.581** (median); worst-case **1.595**  
- `completed_incidents` = 0  
- `completed_arm_runs` = 0

Inherited 49.335 s implied ~583 cycles / 8 h. A generate+evaluate pair is now 108.4 s → ~266 pairs / 8 h. Evaluate-only is cheaper than the inherited figure. Phrase "as many as possible" does not appear in the plan.

Descope ladder: delayed timing, then SC-04, then SC-03; stop at SC-01+SC-02+full ablation.

---

## 11. Task bundles

| Task | Bundle | One-line result |
| --- | --- | --- |
| W001 | `logs/review/W001/` | Preconditions; inverted P0.1 anti-goals corrected; git open |
| W002 | `logs/review/W002/` | Two contracts + schema frozen; hashes above |
| W003 | `logs/review/W003/` | Writer; no coercion; close → 0444 |
| W004 | `logs/review/W004/` | Ledger verify + barrier; T1 host hashes identical |
| W005 | `logs/review/W005/` | Workload + manifest; 1080 == DB count on dedicated run |
| W006 | `logs/review/W006/` | Injector; timing ±2 s; lab_agent isolation 12/12 |
| W007 | `logs/review/W007/` | Oracle; independent cross-check; off-by-one demo |
| W008 | `logs/review/W008/` | Two-phase + stubs; GT hash identical ×3; provenance leak demo |
| W009 | `logs/review/W009/` | Throughput; plan JSON fields; `--repeats 1` refused |
| W010 | `logs/review/W010/` | Gate 24/24; oracle-aside and one-byte freeze both went red |

---

## 12. Operational warnings (carry forward + P1)

1. **Stop PostgreSQL before `lab-reset`.** Live cluster → exit 2, no rollback. Reset restarts the cluster.
2. **One slot, one consumer, database `labdb`.** Never recreate `lab_slot` in `postgres`.
3. After T1/T2 the slot rewinds with PGDATA; the host ledger does not. **`lab-barrier` is mandatory** after every harness reset.
4. Guest `/tmp` is `noexec`. Do not remount it.
5. `lab.env` values containing spaces are quoted.
6. No test hatches in boundary components (Article XII). No judging acceptance by a token in prose (Article XIII).
7. **`bin/lab-verify` does not export sourced keys.** Invoke `set -a; source etc/lab.env; set +a; bin/lab-verify --json`. Same for `lab-verify-p1` if you call the `.py` directly; the wrapper sources `lab.env`.
8. **`bin/lab-consumer status` requires an incident id.** Discover it from `ARCHIVE_CURRENT`.
9. Consumer unit is `disabled`. After reboot or idle, start it and wait for `--check` 0. If `invalidation_reason=wal_removed`, roll back to a snapshot that still contains the slot (t1/t2) rather than creating a new slot in the wrong database.
10. Do not print private keys. Never write outside `/home/mlasota/thesis` on the host.
11. `lab-evaluate-arm` / `lab-verify-p1` extra that starts the consumer **must restore `db.jsonl`** afterwards.
12. Do not redirect `lab-verify-p1 --json` onto `logs/review/W010/verify-p1.json` — the runner already writes that path.

---

## 13. Known limitations (carried into P2)

1. Restore and validation are **stubbed**. No recovery-correctness claim is supported until P4.
2. The oracle is **SC-01-specific**. SC-03/SC-04 need a different optimum (earliest malicious commit + corrupted-row set).
3. Cycle times were measured on an otherwise idle 24-CPU host (loadavg ~1.1–1.9). The plan is a floor.
4. `token_count` and `evidence_bytes_presented` are present but null through P1–P4.

---

## 14. P2 go / no-go and what P2 must not do

**P1.1 X006 (2026-08-21).** The next line was true of the P1 instruments gate and is **not** P2’s entry condition. P2 starts when `bin/lab-ready` exits 0. See `docs/P1.1-architecture-handoff.md`.

**Go (P1 instruments).** P1 may be treated as complete. P2 capture work waits on `lab-ready`.

The ledger schema P2 must not deviate from: wal2json JSONL at `evidence/<scenario>/<incident>/db.jsonl`, format-version 2, no transform, with per-incident LSN idempotency and open/close containment as frozen in `contracts/ledger-integrity.md`. P2 collectors **attach files beside that stream**; they do not rewrite it, do not invent a second log format, and do not parse WAL with `pg_waldump`.

P2 must not: ranking, representations, model, real restore, SC-02/03/04 damage, DuckDB as a server, or a live `inotify`/`fanotify` daemon (Article V). `zfs diff` after the fact is the filesystem change evidence (already proven in P0 T013).

P2 specs are **not in the tree yet**. Do not invent them. Wait for the P2 SDD package.

---

## 15. Where to read next

1. `docs/p1-acceptance-memo.md` — machine-readable limitation block at the top  
2. `docs/sample-size-plan.md` and `docs/throughput.json`  
3. `sdd/specs/P1-ground-truth-harness/{spec,plan,tasks,checklist}.md`  
4. Frozen contracts: three P0 + two P1 + `etc/results-row.schema.json`  
5. `sdd/.specify/memory/constitution.md` — Articles I, II, V, VI, VIII, XII, XIII (XIV is in `docs/P1.1-architecture-handoff.md`)  
6. Spot-check `logs/review/W007/cross_check.py`, `W008/fixed-incident-proof.md`, `W008/provenance-leak-demo.md`, `W010/verify-p1.json`, `W010/gate-negative-tests.md`  
7. Stub interfaces: `logs/review/W008/stub-interfaces.md`

Backup: `bin/lab-repomix-backup` → `backups/thesis-p1-<UTC>.md` and `backups/repomix-latest.md`. Pack includes `lib/` and `sql/` (P1 implementation). WAL archive, evidence jsonl, results jsonl, and keys remain excluded.
