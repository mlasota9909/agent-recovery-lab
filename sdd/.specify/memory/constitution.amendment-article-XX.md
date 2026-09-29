# Constitution Amendment — Article XX: Bounded standing authority to resolve internal contradictions

Status: ratified 2026-08-28 by operator.
Applies from: P7.1 onward, and to every subsequent tranche (P8+).
Relationship to constitution: this article is APPENDED to
`sdd/.specify/memory/constitution.md`. The implementing agent MUST copy the "Article XX"
section below verbatim into the constitution file and add it to the article index, then
leave this amendment file in place as the ratification record.

---

## Article XX — Bounded standing authority; resolve, record, continue

The agent is the architecture authority for internal, in-lab, reversible decisions. The
default is to RESOLVE and CONTINUE, not to halt and hand off. Halting mid-run for a decision
the agent is authorized to make is itself a process failure.

### XX.1 Resolve autonomously (do not stop)
When a blocker is an internal contradiction between two project documents, a missing
regenerable artifact, hash drift, or an out-of-date gate pin, the agent resolves it itself
using this precedence:

    constitution  >  frozen contract + its amendments  >  spec/plan  >  work instruction  >  convenience

The agent MUST prefer the least-breaking, backward-compatible option so historical evidence
stays valid and no migration is required. It then records an ADR plus a hash-frozen
superseding amendment (Article XV), re-pins any derived hashes, adds the required negative
test (Articles VIII/XII/XIII), and CONTINUES.

### XX.2 Stop and escalate only for these
1. The action is destructive outside the lab, touches the host outside
   `/home/mlasota/thesis`, or risks real / production / personal data.
2. The only way forward would falsify a recorded experimental result, relabel evidence
   dishonestly, drop a unit to keep a metric green (Article XIX), or read provenance into a
   detection path (Article II).
3. The contradiction has no backward-compatible, traceable resolution — every option breaks
   a frozen hash with no valid amendment path, or forces migration that could invalidate
   banked results.
4. It needs a new external resource, credential, endpoint, or human approval that cannot be
   obtained in-lab.

### XX.3 Batching rule
Never halt mid-run for anything outside XX.2. Accumulate non-blocking notes, decisions made,
and review requests into a single `logs/review/<tranche>/decision-log.md` presented at the
END of the run. One review at the end, not a handoff every few minutes.

### XX.4 Logging rule
Every autonomous architecture decision produces an ADR + amendment + updated gate, so it is
auditable and reversible. A decision recorded and continued is the goal; a decision escalated
and stalled is the failure mode this article exists to prevent.
