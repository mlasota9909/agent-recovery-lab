# File-level answer reading (P12 ADR-7)

`bin/lab-fl-read-answer --completion <text-file> --view <view-file>` reads only
these two files. The view may be the saved prompt, model-view JSON or content
text. It emits one JSON object; it never consults an incident directory, reference,
oracle, damage manifest, representation label or scoring result.

The sole semantic inputs to `extract` are `completion` and `content`. Visible
locators come only from the explicit first-line interval catalogue described in
`fl-inputs.md`. All body paths, prose, incidental timestamps and metadata fields
are ignored for indexing. Recorded names must be nonempty ASCII letters, digits,
periods, underscores or hyphens. Catalogues require positive unique interval
numbers in increasing order, increasing and nonoverlapping times, one consistent
time per snapshot name and one name per time. Consecutive intervals must share
their common boundary. Invalid catalogues produce a rule rejection.

1. A tagged line is a line whose trimmed text starts with the case-sensitive tag `COORDINATE` or
   `REFUSAL`, optionally followed by a colon (the Primary Sweep prompt used `COORDINATE:`). Other text
   (reasoning, code fences, blank lines) is allowed, as in the revised answer-reading rules.
2. Exactly one `COORDINATE` line and no `REFUSAL` line is an answer (step 3). Exactly one `REFUSAL` line
   and no `COORDINATE` line yields `declined`, preserving the trimmed reason (possibly empty). Any other
   combination (no tagged line, several `COORDINATE` lines, several `REFUSAL` lines, or both tags)
   yields `rule_rejection`.
3. Split a coordinate body into whitespace-separated locator tokens. Resolve
   each independently:
   - `interval=N`: decimal positive interval number (leading zeroes allowed).
     It must be catalogued; resolve to that interval's start snapshot.
   - `snapshot=name`: exact, case-sensitive match to a catalogued endpoint name.
     Both start and end snapshots are visible.
   - `ts=value`: extended ISO-8601 UTC date-time with seconds, optional 1–6
     fractional digits, and `Z` or `+00:00`. Compare exact microsecond times;
     choose the latest visible snapshot recorded at or before the timestamp.
     No rounding to seconds, interpolation or hidden-snapshot lookup occurs.
     A timestamp earlier than every visible snapshot does not resolve. A time
     in a gap or after the latest visible snapshot resolves to the latest
     qualifying visible snapshot. Other offsets, naive times and invalid dates
     do not resolve.
4. Malformed, unknown, invisible or otherwise unresolved locators are discarded
   with individual reasons. As ADR-7 requires, these do not override agreement
   among successfully resolved locators. Repeated locators are allowed.
5. With no resolved locators, reject. If resolved locators name different
   snapshots, reject. Otherwise accept their single common snapshot. No attempt
   is made here to decide whether that snapshot is safe.

Output always has `outcome` (`accepted`, `rule_rejection`, `declined`), `snapshot`
(a name only for accepted answers, otherwise null), `reason`, and `locators`.
Each attempted locator has `token`, `resolved_snapshot` (name or null) and
`discard_reason` (null for a resolved locator). Declines and structural rejections
have an empty locator list. Declines do not require a valid evidence catalogue.

Example:

```json
{"outcome":"accepted","snapshot":"s2","reason":"all resolved locators agree","locators":[{"token":"interval=3","resolved_snapshot":"s2","discard_reason":null},{"token":"snapshot=missing","resolved_snapshot":null,"discard_reason":"snapshot is not visible"}]}
```

Every parsed outcome exits 0, including declines and rule rejections. Unreadable
files, invalid view containers or ambiguous prompt boundaries exit 2; command
usage errors follow argparse's exit 2. These execution failures are not outcomes.
Prompt extraction requires exactly one correctly ordered pair of evidence markers;
neither the wrapper nor model-view metadata contributes hidden coordinates.
