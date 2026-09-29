# Resume prompt — P7.1 blocker P7.1-L004-SCHEMA-01

You are resuming the experiment at P7.1, blocker `P7.1-L004-SCHEMA-01`. Under Constitution
Article XX you have standing authority to resolve internal, in-lab, reversible architecture
contradictions yourself via the Article XV amendment path. Do NOT stop to write a handoff for
this class of issue; decide, record, and continue.

The authoritative decision and drop-in files are already placed in the repo:
- docs/adr/ADR-P7.1-6-live-heartbeat-coordinate-enum.md
- sdd/specs/P1-ground-truth-harness/contracts/results-row.amendment-1.md
- sdd/specs/P7.1-matrix-isolation/contracts/run-matrix-plan.amendment-2.md
- sdd/.specify/memory/constitution.amendment-article-XX.md  (append Article XX to the constitution)

DECISION (authorized): extend the coordinate `resolved_by` enum with an additive fourth
value `live_heartbeat`, backward compatible, no migration, authorized for all five coordinate
objects (ground_truth, chosen, naive, incident_open, incident_close). Do NOT split into two
fields. Do NOT edit any frozen file in place.

FIRST: append Article XX from the amendment file into sdd/.specify/memory/constitution.md and
add it to the article index. Then, in the two contract amendment files, replace the
"quote the exact superseded clause" placeholders with the real verbatim clause text from the
frozen originals.

IMPLEMENT in order, on a clean tree, committing before producing results:
1. Confirm ADR-P7.1-6 present and authoritative (overwrite any earlier partial).
2. results-row.amendment-1.md present with the real superseded clause quoted; record its sha256.
3. run-matrix-plan.amendment-2.md present with both superseded clauses quoted verbatim.
4. Add live_heartbeat to lib/generate_results_schema.py; regenerate etc/results-row.schema.json.
5. Add live_heartbeat to any hardcoded triple in lib/results_schema.py and to the COORD_FIELDS
   resolved_by check in lib/lab_verify_p1.py.
6. Compute the new schema sha256; grep the old digest
   103eaa92ea48bca7ebcc7ce451b1978d822e92af41dc92b8fbf8f1e7a26d3775 across lib/bin/sdd/docs/logs
   and re-pin EVERY occurrence; update all *contracts-unchanged* expectations to: results-row.md
   byte-identical, amendment present, schema.json at NEW hash.
7. Update WI-L004 L004-1 to accept live_heartbeat with non-zero skew.

NEGATIVE TESTS (must pass): bogus resolved_by (e.g. made_up_source) rejected on every
coordinate field; live_heartbeat with zero skew rejected by L004-1; a pre-amendment lsn_first
fixture row still validates.

DECISION TO RECORD EXPLICITLY: the first rejected field is ground_truth_coordinate, so the
live re-run re-resolves the oracle coordinate live. The enum extension covers this. If you
instead intend ground truth to remain the frozen oracle value (lsn_first), record that as a
separate explicit choice in the decision-log; do not let it silently ride on this change.

THEN: commit clean; bin/lab-matrix --force (re-run all 51 SC-02/03/04 cells; failures become
rows, retained/superseded per Article XIX); bin/lab-verify-p7 (all PASS); bin/lab-regression
(green at NEW hash); produce L004 completeness + validity partition, live-coordinate sample,
provenance-blind scan, dropped-row negative test; continue through L005 and L006.

STOP only per Article XX.2: destructive/out-of-lab/real-data actions; anything that would
falsify results, relabel evidence, drop a unit to keep a metric green, or read provenance into
detection; a contradiction with no backward-compatible resolution; or a needed external
credential/resource. Otherwise proceed and log all decisions to
logs/review/P7.1/decision-log.md.

DONE = lab-verify-p7 all-PASS, regression green at the new hash, prior frozen artifacts
byte-identical, total_rows == total_planned_runs with a validity partition, and a single
decision-log.md presented for review.
