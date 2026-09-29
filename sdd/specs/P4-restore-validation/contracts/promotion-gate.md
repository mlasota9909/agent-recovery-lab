# FROZEN CONTRACT — Promotion Gate (the validate-vs-promote boundary)

**Contract ID:** promotion-gate
**Frozen by:** E001
**Status:** FROZEN — changes only by amendment-through-supersession (Article XV).
**Enforced by:** `bin/lab-promote` (E007); referenced by the restore orchestrator (E004) and the P4 gate (E010).

## 1. Purpose

Restoring a candidate coordinate into a sandbox and *validating* it is safe and repeatable. **Promoting** — replacing
the live/"production" state with the restored state — is destructive and irreversible in a real deployment. This
contract fixes the boundary between the two so that validation can never accidentally promote, and promotion can never
happen without a clean verdict and an explicit human decision. In the lab, promotion is always a simulation.

## 2. Hard rules

- **R1 — validate is not promote.** Running `bin/lab-restore` + `bin/lab-validate` + `bin/lab-verdict` produces a
  report and changes nothing outside the sandbox. It never calls the promotion path.
- **R2 — promotion requires a clean verdict.** `bin/lab-promote` refuses unless `consistency_verdict == "correct"`.
  A `incorrect-safe`, `incorrect-corrupt` or `not-recovered` verdict can never be promoted.
- **R3 — promotion requires explicit authorization.** `bin/lab-promote` refuses unless an explicit operator
  authorization token is supplied. The token is never inferred, defaulted, or derived from the verdict. Absent a
  token, the report's `promotion.decision` is `withheld`.
- **R4 — in the lab, promotion is a logged simulation.** Even with a clean verdict and a valid token, `bin/lab-promote`
  in this environment records what it *would* replace and takes no destructive action: it never overwrites the victim
  cluster or dataset, and never touches the evidence store. `promotion.decision` becomes `simulated`.
- **R5 — restore is read-only w.r.t. victim + evidence.** The entire restore/validate/promote-simulate path only ever
  creates sandbox clusters and `zfs clone` datasets. `zfs rollback` of the victim and any write to the victim PGDATA
  or the evidence root are prohibited and are checked by the before/after manifest (`restore-report.md` §2 R6).
- **R6 — teardown leaves no residue.** Sandbox clusters and clones created for a restore are torn down after use;
  teardown itself must not touch the victim or evidence. A promotion simulation never creates a clone that outlives it.

## 3. Decision values

| `promotion.decision` | When |
| --- | --- |
| `withheld` | no authorization token supplied (the default for every validation-only run) |
| `simulated` | clean verdict + valid token, in the lab: the destructive action is logged, not performed |
| `authorized` | reserved for a real deployment where the destructive promotion would execute — **never emitted in the lab** |

## 4. Promotion record (emitted by `bin/lab-promote`)

| Field | Type | Meaning |
| --- | --- | --- |
| `incident_id` | string | the incident |
| `requested_of` | string | which coordinate source was requested for promotion |
| `consistency_verdict` | string | the verdict being gated on (must be `correct` to proceed) |
| `authorization` | object | `token_supplied` (bool), `authorized_by` (string\|null), `token_ref` (path\|null) |
| `decision` | string | `withheld` / `simulated` / `authorized` (see §3) |
| `simulation` | object | `would_replace` (human description), `action_taken` (must state victim untouched) |
| `safety` | object | `victim_untouched` (bool), `evidence_untouched` (bool) |

## 5. Example (illustrative, non-normative)

```json
{
  "incident_id": "SC-01-20260825T0100Z-a1",
  "requested_of": "ground_truth",
  "consistency_verdict": "correct",
  "authorization": {
    "token_supplied": true,
    "authorized_by": "operator:mlasota",
    "token_ref": "logs/review/E007/promo-token.txt"
  },
  "decision": "simulated",
  "simulation": {
    "would_replace": "labpool/victim/protected + labdb cluster",
    "action_taken": "logged only; victim untouched"
  },
  "safety": {
    "victim_untouched": true,
    "evidence_untouched": true
  }
}
```

## 6. Change control

Frozen at E001 and hash-recorded in `logs/review/E001/`. Later changes supersede via `promotion-gate.amendment-N.md`
with its own ADR; this file stays byte-identical (Article XV).
