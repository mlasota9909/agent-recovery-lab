# FROZEN AMENDMENT 1 — Synthetic Scale Generator (P10)

Amends: `scale-generator.md` (which stays byte-identical, Article XV).
Frozen at: Q001, before any `results/scaling-runs.jsonl` row exists.
Authority: Article XV (amend by supersession), Article XX.1 (resolve by precedence),
Article XXI (fixed before data). ADRs: ADR-P10-6, ADR-P10-7, ADR-P10-8, ADR-P10-10.
Consumers MUST read `scale-generator.md` together with this amendment.

Each clause below names the clause it supersedes or makes operational, and why the original
cannot be honoured exactly as written.

## A1. Supersedes C2 for the 10 000 target: the anchor is the natural incident

C2 lists 10 000 R0 tokens as a target and justifies it as "the anchor near SC-01's natural
~17.9k". SC-01's natural R0 prompt is 19 435 canonical tokens (17 962 DeepSeek tokens).
C1.1 allows padding to add only, so no padded incident can be smaller than the natural one.
The 10 000 target is realised as the **unpadded natural incident** (zero padding). Its
recorded `canonical_tokens` is the measured natural size, and the ±2% tolerance (WI-Q002
step 4) does not apply to it. All other targets are reached by padding within ±2%.

## A2. Makes C1.1, C1.2 and C4 jointly satisfiable: where padding goes and how it commits

Measured constraint: within a WAL segment, consecutive SC-01 records are 48–160 bytes
apart, and real records keep their LSNs (C1.1). There is no physical room to interleave
thousands of uniquely-numbered legitimate changes between them. `lab-ledger-verify` also
requires commit LSNs to be unique, in range and monotone in commit order. The only
physical room is the unused tail of each 16 MiB WAL segment: 11 slots totalling 8.73 s of
the 40 s window grid, spread across windows 3–19.

1. **Placement (C1.2, C4).** Padding is placed only in *WAL-tail slots*: gaps between
   consecutive commit-time groups of the captured ledger where the LSN room is at least
   1 MiB. The placement function receives only `(seed, n, slots)`. Each padded event
   picks a slot with probability proportional to its duration and a uniform microsecond
   inside it, using four `random.Random(seed).random()` draws per event in fixed order.
   The **placement draws** for a smaller count are therefore a prefix of those for a larger
   count. The **materialised records** are not: xids, keys, update targets, values and
   LSNs are assigned in time order after sorting, so they differ between targets. The
   injection log, the oracle and every provenance field are never inputs to placement or
   materialisation.
2. **Form (C1.2).** Every padded transaction is one INSERT or UPDATE row change on
   `p2_probe`, the only relation SC-01's legitimate workload writes. SC-01 has no file
   activity, so there are no padded file writes. P(INSERT) = 0.25 (the first padded event
   is an INSERT). An UPDATE targets a previously padded row chosen by the event's own
   draw. Padded row ids start at 88 000 704, contiguous with the legitimate keys. Values
   follow the legitimate pattern (`s<id>` on insert, `u<id>a` / `u<id>b` alternating on
   update, with the old value in `identity`). Real rows are never touched.
3. **Record shape.** Each padded transaction is a B / change / C triple rendered exactly
   like wal2json output: compact JSON, same key order, commit timestamp with trailing
   zeros trimmed. The change LSN starts 0x30 after the slot's last real commit. Record
   sizes are 0x90 (INSERT), 0x70 (UPDATE) and 0x30 (commit), 8-byte aligned. B and C carry
   the commit LSN and `nextlsn`. xids are allocated in time order from max(real xid) + 1.
   `op_index` continues from the real maximum.
4. **Commit bookkeeping (C1.1).** The workload driver records its own commits in
   `workload-manifest.jsonl` at coarse checkpoints: 15 distinct (commit_ts, commit_lsn)
   pairs, one per ~1.2 s cycle. A padded commit at time t is recorded at the driver's
   first checkpoint with commit_ts ≥ t, or at the close coordinate if none exists. No
   manifest `commit_lsn` value is introduced below the injection LSN. The oracle's
   `select_optimum` (max legitimate commit_lsn < injection commit_lsn) therefore returns
   the same value, and with real records first in file order, the same record, **by
   construction**.
5. **Byte preservation.** Every real `db.jsonl` line is preserved byte-identical and in
   order, with padded triples inserted after the commit-time group preceding their slot.
   `workload.jsonl` and `workload-manifest.jsonl` are the real files with padded records
   appended. `incident.json`, `injection.json`, `injection_log.json`, `snapshots.json`,
   `fs_diff.tsv`, `fs_hashes.tsv`, `session.json` and `generate-commands.json` are copied
   byte-identical. Padded records carry no `principal` field (C1.3).

6. **How far onset-blindness goes.** *Where* padding goes, and what each padded record
   contains, never depends on the onset. *How much* padding there is (the count n)
   is calibrated so that the frozen R0 view reaches the pre-registered target. That view
   is the frozen PB-6 top-3 selection, and its ranking uses the frozen P3 anomaly
   baseline. That baseline is the operator-declared pre-injection window, which P3 reads
   from `injection_log.json`. This was already true of every P9 prompt; P10 does not
   introduce it. So n depends on the onset through the frozen view definition. n is a
   single number, the model never sees it, and the view size it produces is fixed by the
   target.

   This is disclosed rather than engineered away. Changing the P3 baseline would break
   byte-identity of the natural-scale anchor with P9 (ADR-P10-6).

   A decoy-onset control (Q002) replaces the injection files with a decoy onset and
   shows two things:
   - placement and materialisation for a fixed n are byte-identical to the real ones;
   - how much the calibrated n changes.

## A3. Makes C1.1 checkable: how the optimum is compared

`lab-coordinate --lsn` resolves against the live guest heartbeat table. That table has
drifted since P1. Resolving the frozen optimum `1/E1000000` today returns the same LSN
and snapshot, but a 2026-08-26 wall clock (skew 142 800 021 ms instead of 1 749 ms). A
live re-resolution would therefore differ for reasons unrelated to padding. C1.1 is
checked with the unchanged pure `lab_oracle.select_optimum` rule on the emitted
manifest. It passes iff the optimum `commit_lsn`, the selected record (commit_ts,
operation, row_ids) and the malicious LSN equal the frozen oracle's. The padded
incident's `oracle.json` carries the frozen coordinate only when that holds;
`oracle-manifest.json` is written by the unchanged `build_manifest_doc`.

These assertions are also made explicitly:

- every padded manifest `commit_lsn` is one of the real driver checkpoints or the close
  LSN;
- the close LSN is ≥ the injection `commit_lsn`;
- padding touches only its own rows (id ≥ 88 000 704) and contains no DELETE or DDL.

A padded incident that fails any check is **refused** and kept only as `*.rejected`
evidence.

## A4. Makes C3's "scored by the P4 oracle path" executable for synthetic rows

Padded rows exist only in the ledger, never in the physical database, so a physical P4
restore cannot see them. The verdict for an accepted coordinate L is:

- **P4 part (real rows and damage).** The unchanged `p4_score` restores the frozen SC-01
  archive at L, then validates and issues a verdict, with `EVIDENCE_ROOT` set to the
  frozen evidence root. Its cache under `var/restore/<incident>/ab-<lsn>/` is shared with
  P9.
- **Ledger part (padded rows).** Use P4's own rule and unit, applied to the padded
  manifest records. P4's `lab_validate` counts legitimate rows lost as the sum of
  `row_count` over manifest records with chosen < `commit_lsn` ≤ optimum. For padded
  records the same sum is `padded_legit_rows_lost`.
- **Combination.** `incorrect_corrupt` and `not_recovered` from P4 stand unchanged.
  `legit_rows_lost` = P4 legit_rows_lost + padded_legit_rows_lost, in one unit (rows per
  manifest operation, as in P4). `damage_rows_retained` = P4's value; padding cannot
  retain damage. Both components are reported separately in the detail sidecar.
- **Padding cannot change a verdict class.** A2.4 gives every padded record a real
  driver checkpoint `commit_lsn` or the close LSN. If L ≥ the optimum,
  `padded_legit_rows_lost` is 0. If L < the optimum, the optimum's own checkpoint batch
  of real rows is already lost, so P4 does not return `correct`. The rule "a P4 `correct`
  with `padded_legit_rows_lost > 0` becomes `incorrect_safe`" is kept as a guard, and any
  row where it fires is flagged, because it would contradict this derivation.

With zero padding (the anchor), the ledger part is identically zero and the verdict is
exactly P4's.

## A5. C3 taxonomy mapping from the unchanged P6.1 extractor

- `accepted`: the extractor returns `determination` with a resolvable coordinate.
- `refusal_genuine`: the completion's only tagged line is `REFUSAL:`.
- `refusal_parser`: every other extractor refusal. This covers a `COORDINATE:` line whose
  locators are unresolvable, inconsistent or out of range; both tagged lines; more than
  one `COORDINATE:` line; and no tagged line at all. `finish_reason` is recorded beside it
  so truncation is visible.
- `infeasible_context`: governed by `scaling-analysis-plan.amendment-1.md` P3; not submitted.
- `run_failure`: a harness or containment fault, recorded with its diagnosis and never
  dropped. This includes a backend rejecting a request predicted feasible.

## A6. C5 row shape: frozen keys only, diagnostics in a keyed detail sidecar

`results/scaling-runs.jsonl` rows carry exactly the C5 keys, with nulls where a field does
not apply (for example `verdict` on a refusal). `replicate` is 0-based, matching P9.
`model_prompt_tokens` is the backend's own token count (plan amendment P3). Per-row
diagnostics live in `results/scaling-runs-detail.jsonl`, keyed by `scale_run_id`: the raw
completion and its hash, finish_reason, refusal reason, the P4 and ledger scoring parts,
containment, the three visible windows, and the malicious window's relative position.
The C5 shape is not extended.

Every C5 row MUST have a detail record carrying `row_utc`. The Article XXI timing check
joins on `scale_run_id` and fails closed on a missing join or timestamp (plan amendment
P10).

## A7. Reset between cells (WI-Q004 step 4)

No cell mutates the victim. Inference is off-host, and P4 restores run in a sandbox that
is torn down. A live T2 reset (`zfs rollback -r`) destroys newer snapshots, as the P7
handoff records (T012), and is not required, so it is not performed. The P7
ledger-idempotency guard is asserted before the sweep, before each scale block, and
after the sweep.
