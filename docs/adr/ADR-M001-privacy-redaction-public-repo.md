# ADR-M001 — Redact internal-network IPs before public disclosure

Status: accepted 2026-09-22 (post-P9, maintenance action; the repository was published to
a public GitHub remote)
Authority: Article XX (resolve, record, continue), Article XV (amend a frozen artefact by
supersession, re-pin every derived hash in lockstep).

## Context

The repository was pushed to a public GitHub remote. It contained real private-network and
Tailscale CGNAT addresses for the lab's hosts (`thesisvm01`, `gb10a`, `alienware`, `c220m3`,
`gympc`) across ~60 tracked files: documentation, ADRs, library code, the live environment
file (`etc/lab.env`), P9 runtime records, and historical `logs/review/*` snapshots. None of
these addresses are internet-routable or independently exploitable (RFC-1918 / CGNAT), but
they reveal the operator's home-lab topology and device naming.

Two of the affected files are frozen contracts with a hash pinned into live verification
code: `sdd/specs/P0-lab-substrate/contracts/lab-env.md` (an illustrative `VM_ADDR` example)
and `sdd/specs/P6-arm-b-model-harness/contracts/model-runtime.amendment-1.md` (the real
`gb10a` backend address). A third apparent pin
(`H001_P6_RUNTIME_AMENDMENT` in `lib/lab_p61.py`, checked by `lab_verify_p61.ac17`) was found
to already reference the **P6.1** amendment file's digest, not the P6 file inspected here —
a pre-existing mismatch unrelated to this change, not exercised by `bin/lab-regression`,
`lab-verify-p7`, `lab-verify-p7.1`, or `lab-verify-p8`/`p9`, and left as-is.

## Decision

1. Every real host IP in every tracked file was replaced with an address from
   `203.0.113.0/24` (RFC 5737 TEST-NET-3, reserved for documentation), one placeholder per
   real address, applied consistently everywhere that address occurred. Generic CIDR range
   literals (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `100.64.0.0/10`) were left
   untouched — they are not host-identifying.
2. Historical `logs/review/*` snapshots and narrative logs had their embedded IP **text**
   redacted the same way. No recorded PASS/FAIL verdict, digest, count, or other measured
   data point in any historical record was altered — only incidentally-embedded address
   strings.
3. `sdd/specs/P0-lab-substrate/contracts/lab-env.md` was edited in place (its one-line
   `VM_ADDR` example), its SHA-256 recomputed, and every live reference to the old digest
   re-pinned to the new one in lockstep: `lib/lab_p51.py`, `lib/lab_verify_p11.py`,
   `lib/lab_verify_p2.py`, `lib/lab_verify_p21.py`, `lib/lab_verify_p3.py`,
   `lib/lab_verify_p31.py`. This is the one deliberate exception to "an original frozen file
   stays byte-identical" (Article XV): a live, real network address baked into a contract is
   the kind of accidental-disclosure defect the file-freezing discipline was never meant to
   protect. `bin/lab-verify-p2` and the full P9 terminal gate were re-run to confirm every
   dependent hash check still passes.
4. `sdd/specs/P6-arm-b-model-harness/contracts/model-runtime.amendment-1.md` was edited the
   same way; no live code compares its digest to a fixed pin (see Context), so no re-pin was
   needed.
5. `etc/lab.env` (the live, machine-specific environment file `lab-discover` keeps
   synchronised to the real lab) was removed from git tracking and gitignored;
   `etc/lab.env.example` — a redacted template — is tracked in its place. The local file on
   disk keeps its real values; only the git history from this commit forward stops carrying
   them. `lib/lab_verify_p2.py`'s `ENV_COMMENTS["LAB_HOSTS"]` (the comment `lab-discover`
   re-inserts after stripping) was updated to the redacted text, since that string lives in
   tracked, public source.
6. `runtime/p9-model-set.json` / `runtime/p9-model-verify.json` (P9's closed-out registry)
   had their real backend URLs redacted the same way. P9 is closed with no further
   experiment planned against these specific hosts; a future `lab-p9-modelset --build`
   would regenerate them with live values on disk without re-exposing anything, since
   `etc/lab.env`-style untracking does not apply here (these stay tracked as historical
   record) — a future edit reintroducing real IPs into a commit would need the same
   redaction pass repeated.

## What this does **not** cover

Real addresses remain visible in this repository's git history **prior to** this commit
(every commit from the initial public push onward) — this was a forward-looking redaction
of tracked content, not a `git filter-repo` history rewrite. That heavier, disruptive
option (rewrites every commit SHA, forces a push, breaks any existing clone) was
deliberately not taken; see the operator's own record of that decision for the reasoning.

## Consequences

- `bin/lab-verify-p2`, `bin/lab-regression`, `lab-verify-p7`, `lab-verify-p7.1`,
  `lab-verify-p8`, and the P9 terminal gate (`bin/lab-verify-p9`) all re-run green after this
  change.
- No frozen contract's *substantive* content (the fields Article I–XXI care about:
  determinism rules, schema shape, decoding parameters, statistical tests) changed — only
  one illustrative/real IP literal in each of the two affected files.
- Anyone cloning the repository from this commit forward, and copying
  `etc/lab.env.example` to `etc/lab.env`, gets a working template with no real network
  details; they fill in their own.
