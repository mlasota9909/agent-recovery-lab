# ADR-P11-1: freeze a view-only grammar and a finite analysis

Status: accepted under Article XX, before any P11 completion parse.

## Evidence inspected

The frozen prompt template and the R0/R2 prompts at the natural anchor were
read. R0 contains change LSNs and change timestamps, without commit records or
the heartbeat table. R2 shows windows 14, 15 and 16 with endpoints. The old
extractor reads a hidden window index and a live heartbeat lookup. That cannot
satisfy P11 G1's requirement to consume only the supplied model view.

Metadata inspection found 356 joined P10 main/detail rows, 161 occurrences
carrying a completion and 210 current planned units. It did not inspect or
re-parse the completion text. Six duplicate unit occurrences are retained.
The P10 handoff and recorded gate report also document a pre-existing failed
P0 live regression. P11 must preserve that fact.

## Decision

Keep both original P11 contracts byte-identical. Apply and freeze
`answer-grammar.amendment-1.md` and `rescore-analysis-plan.amendment-1.md` with
them. Use only visible positions. Recognise the omitted window syntax without
reading an invisible predecessor. Timestamp resolution requires an explicit
visible commit and records the absence of that evidence. This is a stricter
boundary than P6.1 for some answers, so every changed outcome is reported.

Audit all 161 retained completion occurrences. Inferential analysis uses the
existing last-attempt rule, with historical attempts retained separately.
Fix denominators, independent endpoint resampling, the three-comparison
correction and missing-data rules now. Make one finite confirmatory batch of
the shortfall N per cell. Do not submit repeatedly until five answers happen
to be accepted. Interpret a null difference as no detected difference at the
tested points, not proof of equivalence everywhere in a context window.

The P11 implementation extends only the dispatch of `lab-prereg-check`;
its default P10 behaviour is preserved. P4 scoring and P9 statistics stay
unchanged. Prior gate invocations use a scratch copy to preserve their fixed
output paths. A pre-existing failed prior gate remains a failed requirement,
not an automatic waiver. No live reset is authorised by an acceptance check.

## Proof obligations

R001 pins original and amendment hashes and UTC before any re-score file,
and rejects a backdated scratch file. R002 tests agreement, missing commits,
missing predecessors, conflicting locators, determinism, oracle-access taint
and representation parity. R003 checks all source occurrences and unchanged
coordinate verdicts. R005 rejects tampered originals or amendments. R007
compares prior artefact hashes and reports the actual prior-gate outcome.

The hash table and freeze time below are generated once by R001, before data.

Freeze UTC: 2026-09-25T03:30:57.003449Z

| File | SHA-256 |
|---|---|
| answer-grammar.md | `f1e1916a544f05efbc7eb2567ff2624fa5df6e1ffdf15ab307a671bab67d6769` |
| answer-grammar.amendment-1.md | `ab0e09252464bfe357c51a988378f5985bdbae8ed375419b4370f68077cdc538` |
| rescore-analysis-plan.md | `b82559d5bc47b8e7b366e7ee4f3ad519eaaf54237139d291ed48ecc6c3fb275d` |
| rescore-analysis-plan.amendment-1.md | `6c14ddad5dd9c88df9258dca37e7296551521c23b8971ba06c89015a8921d9da` |

Producer HEAD before freeze: `235e670f3b59964edea6547f15212c0d04561073`.
