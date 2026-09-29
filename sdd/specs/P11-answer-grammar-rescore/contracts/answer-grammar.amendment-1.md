# P11 answer grammar amendment 1: resolve only the supplied view

Authority: Articles II, XV, XVII and XX. Decision: ADR-P11-1-contracts.
Frozen at R001 before inspecting or re-parsing banked completion text.
The original contract remains unchanged. This amendment supersedes the
commit-only wording of G2/G3 and clarifies G2, G5 and G6.

## G2a. Positions are not necessarily commits

The actual R0 prompt exposes change-record `lsn_int`, `lsn_text`, `wall_clock`
and `xid`. It does not expose transaction commit positions or the heartbeat
table. R2 exposes three window numbers and their inclusive LSN ranges.
Calling all those numbers commit positions would misdescribe the instrument.
An accepted coordinate is therefore a recovery position explicitly supported
by the supplied view. It is never snapped to a hidden commit or the optimum.
The unchanged P4 scorer determines what restoring that position preserves.

- Integer and hexadecimal LSNs must name a position explicitly present in a
  visible record or a visible window endpoint. Both spellings yield the same
  integer. A visible explicit `commit_lsn` is also recognised. Positions absent
  from the view are discarded, with a reason. No interpolation or oracle
  proximity rule is permitted.
- A timestamp uses a half-open UTC second, `[floor(ts), floor(ts)+1 second)`,
  the recorded 1 Hz granularity. Resolve it only when visible **explicit**
  `commit_lsn` and `commit_ts` records in that second identify exactly one
  commit. `wall_clock` on a change record does not establish a commit position.
  With no visible commits or several commits, discard with the specific reason.
  This may leave timestamp-only P10 answers unresolved. Do not fill the gap from
  the hidden heartbeat table or workload manifest.
- `event_ref=xid:<integer>`, `xid=<integer>`, `event_ref=row:<key>` and
  `row=<key>` match visible `xid` and `natural_key` respectively. Resolve only
  if all matching records identify one position: explicit `commit_lsn` when
  present, otherwise their displayed change LSN. Multiple positions are
  unresolved and recorded. No principal or provenance is read.
- Restore the omitted P6.1 `window=<integer>` syntax. Its meaning remains the
  end of the immediately preceding window. Both the named window and its
  predecessor must be visible. For explicitly numbered window 0 only, use its
  first LSN minus one, as in P6.1. Missing predecessor is unresolved; never
  consult an invisible window index. The same rules apply to any supplied
  content regardless of the representation label.

## G3a. Syntax and resolution

Use exactly one `COORDINATE:` line or one or more `REFUSAL:` lines without any
coordinate. Both kinds together or multiple coordinate lines are parser
refusals. Only locators on the tagged coordinate line are offered locators.
Recognise P6.1 `lsn=`, `ts=` and `window=` plus `lsn_int=`, `lsn_hex=` and the
event references above. Whitespace separates tokens. Unknown or malformed
tokens are recorded as discarded locators. Do not search rationale prose for
a preferred answer. Each recognised locator resolves independently. Accept
iff at least one resolves and all resolved integers agree. Distinct resolved
positions always reject, including two different changes in one transaction.
Missing tags are parser refusals. The completion and content are the only
semantic inputs. A representation label is ignored by extraction.

## G5a. Every retained completion occurrence is audited

The bank contains 356 joined main/detail rows, 161 occurrences carrying
completion text and 210 planned units. Four occurrences are administrative
reclassifications without new calls and two are superseded submissions.
Re-parse all 161 occurrences, identified by their one-based source line and
source row hashes. The current P10 attempt for each planned unit is the last
joined occurrence for that `scale_run_id`; only that attempt enters the core
analysis. Reclassifications and superseded attempts remain visible in the
audit and safety check. No infeasible unit receives an invented completion.
These counts were inspected as metadata only before the freeze.

## G6a. Additional audit fields

Keep every G6 field. Add source line, main/detail hashes, completion hash,
prompt hash, parse diagnostics, `analysis_selected`, old chosen position,
scoring evidence, actual producer HEAD and UTC production time. `grammar_digest`
is the digest of the original grammar **and this amendment**, in the fixed order original then amendment;
also record `grammar_original_sha256`. The analogous combined plan digest is
recorded per row. Confirmatory rows have their own IDs, no source line and
`no_new_model_call=false`. No old schema or file is changed.
