You are an experimental subject. Locate a recovery snapshot from the evidence below.
Use only this evidence. You are not given a reference answer.

Task: identify the latest safe recorded snapshot before damaging file activity began.
Name that snapshot using whichever locator the evidence provides: an interval index,
a snapshot name, or an ISO-8601 UTC timestamp. An interval locator means its start
snapshot. A timestamp means the latest visible snapshot recorded at or before it.
The interval catalogue lists the visible snapshot names and their recorded times.
Refuse only when the evidence does not let you localise a safe snapshot.

Evidence:
<<<FL_CONTENT
{content}
FL_CONTENT>>>

End with exactly one tagged line and nothing after it, in one of these two forms:
COORDINATE: <locator> [<locator> ...]
where each locator is one of interval=<N>, snapshot=<name>, ts=<ISO-8601 UTC>
REFUSAL: <reason>

All locators that resolve must identify the same snapshot. Timestamps must include Z or +00:00.
If the evidence does not localise a safe snapshot, refuse. Do not guess.
