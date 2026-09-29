# Plan — P0.1: P0 Remediation

Architecture and locked decisions for the remediation tranche. Do not re-litigate these; if one is wrong, stop and
report.

## 1. Position of this tranche

P0 built the substrate. P0.1 makes two of P0's claims survive inspection. No new capability, no contract change, no
P1 work. Everything here is a repair with a proof attached.

The P0 build's quality is not in question. Two of its findings were genuinely good work and are preserved
untouched: the deepest-first child rollback in `bin/lab-reset` (because `zfs rollback -r` on a parent does not restore
descendant dataset contents — a defect that would have silently corrupted every reset), and the paired `sql_drop`
event trigger that makes `DROP` visible in the DDL audit trail. Neither is modified here.

## 2. Decisions

### ADR-P01-1 — Remove the hatch; do not gate it harder

**Decision.** Delete both `t009-*` branches from `bin/lab-wal-receive` outright. Do not replace them with a
better-guarded flag, a root-only sentinel, a compile-time switch or an environment variable.

**Rationale.** The defect is not that the hatch is poorly guarded. The defect is that a boundary component contains a
code path that widens the boundary at all. Anyone assessing the isolation claim reads the script; any
conditional read path invalidates the claim regardless of its guard. Constitution Article XII now prohibits the class.

**Consequence.** The isolation suite loses its red-phase mechanism and must acquire a new one outside the component.
See ADR-P01-2.

### ADR-P01-2 — Regression by host-side mutation, in preference order

**Decision.** The isolation suite's red phase mutates host state that `lab-wal-receive` does not read. Two permitted
mechanisms, in this order of preference:

1. **Preferred — permission mutation.** Create a scratch file under `EVIDENCE_ROOT`, chown/chmod it so a victim
   principal can genuinely read it, re-run the suite, require FAIL, restore mode and ownership, require PASS.
2. **Fallback — authorised-key mutation.** Add a temporary, clearly-labelled authorised-key entry for the guest
   principal *without* a forced command, so an unrestricted channel genuinely exists; re-run, require FAIL; remove the
   entry and destroy the keypair; require PASS.

**Rationale.** Both create a real, externally-caused violation, which is what a regression test is supposed to
simulate. Mechanism 1 is preferred because it touches nothing security-relevant beyond a scratch file and reverts by
`chmod`. Mechanism 2 exercises the channel more faithfully but manipulates key material, so it carries a cleanup
obligation that must be asserted.

**Consequence.** The suite must be able to revert cleanly and prove it. Any temporary key is destroyed in the same
invocation and its absence asserted.

### ADR-P01-3 — Enumeration test, so the hatch cannot return

**Decision.** Add a command-surface enumeration test to the isolation suite: a fixed corpus of candidate
`SSH_ORIGINAL_COMMAND` values, each asserted to be refused except the intended append class. The corpus explicitly
includes the removed probe string.

**Rationale.** Deleting the hatch fixes today. The enumeration test fixes tomorrow: if anyone re-adds a magic
command, the test goes red. This is the durable half of the repair and the artefact worth keeping as evidence, since
it converts "we removed a hatch" into "the channel's accepted surface is enumerated and tested".

**Corpus MUST include.** The removed probe string; `append` with a traversal path (`../`), an absolute path, and a
path containing a null-ish or shell metacharacter; `append` with no argument; a second verb (`read`, `cat`, `list`);
an empty command; a compound command (`append x; cat /etc/passwd`); a command with a newline; a legitimate append of
an already-present segment (must be refused as overwrite); and a legitimate append of a new segment (must succeed).

### ADR-P01-4 — Consumer is a supervised systemd unit on the host

**Decision.** The persistent `pg_recvlogical` consumer runs as a host-side systemd unit, started when an incident
opens and stopped at teardown, with `Restart=always` and a short `RestartSec`. It writes `db.jsonl` into the current
incident's evidence directory.

**Rationale.** Host-side keeps the pull-based evidence architecture intact — the victim gains no new outward path, so
ADR-002's isolation argument is unchanged. systemd gives supervision, restart and liveness detection without writing
a supervisor. Constitution Article V bans bespoke daemons and job queues; a unit file is stock platform, not a
service framework.

**Consequence.** Opening an incident becomes conditional on consumer liveness (FR-3.5). This is deliberate: an
incident captured without a consumer is an incident with no database evidence, and must fail at open rather than be
discovered later.

### ADR-P01-5 — Slot lag fails closed

**Decision.** `bin/lab-slot --check` exits non-zero on over-threshold retention, on an inactive slot while an
incident is open, and on an invalidated slot. What was an observation becomes a failure.

**Rationale.** The 436 MB observation passed acceptance because "bounded" was the only assertion. Boundedness is
satisfied right up to the moment the cap invalidates the slot and the evidence stream ends. A warning nobody is
watching during an unattended overnight matrix is not a control.

### ADR-P01-6 — Two tiers, honestly labelled; upgrade only the load-bearing two

**Decision.** All eighteen P0 criteria get a tier. Delete the prose-matching helper. Re-implement AC-6 and AC-14 as
tier M. Leave the remaining seven attested criteria as tier A, but re-point each at a machine-readable field rather
than prose.

**Rationale.** Re-deriving all nine live would be expensive and some are genuinely one-time events. The honest fix is
not to pretend everything is mechanical but to label the difference and to insist the load-bearing ones are
mechanical. AC-6 and AC-14 qualify because a silent regression in either destroys a measurement the experiment depends on
— before-images make "damaged data retained" scoreable, and heartbeat density is the LSN-to-time index that makes a
coordinate resolvable at all — and neither failure would surface until P5.

**Consequence.** `bin/lab-verify` prints per-tier totals. There is no longer a single "18/18" headline, by design.

### ADR-P01-7 — `noexec`-safe live-process test

**Decision.** Prove the reset guard using a process that requires no executable file on a `noexec` mount: hold an
open file descriptor on a file inside `DS_PGDATA` from a shell redirection, or use the running PostgreSQL cluster
itself as the live process, or `sleep` started from an interpreter already on an exec-permitted path.

**Rationale.** The T012 skip was an environment artefact, not an impossibility. The guard protects against rolling a
data directory out from under a running cluster, which would corrupt state in a way that could be mistaken for an
experimental result.

## 3. Component changes

| Component | Change | Task |
| --- | --- | --- |
| `.specify/memory/constitution.md` | Append Articles XII and XIII | R001 |
| `bin/lab-wal-receive` | Delete both `t009-*` branches; no other change | R002 |
| `bin/lab-isolation-test` | New host-side regression mechanism; add enumeration corpus | R002 |
| `bin/lab-consumer` (new) | Start/stop/status for the decoding consumer | R003 |
| `lab-consumer@.service` (new) | systemd unit, host, `Restart=always` | R003 |
| `bin/lab-incident` | Precondition: consumer live before open | R003 |
| `bin/lab-slot` | `--check` fails closed on three conditions | R003 |
| `bin/lab-verify` | Tier labels, per-tier totals, `--json`, delete prose matcher | R004 |
| `bin/lab-verify` AC-6, AC-14 | Re-implement as live mechanical checks | R004 |
| `bin/lab-reset` | No functional change; guard proven by new test | R005 |
| `etc/lab.env` | Add pinned versions and steady-state retention | R006 |
| `docs/environment.md` (new) | Generated from `lab.env` | R006 |

## 4. What must not change

- Anything under `specs/P0-lab-substrate/contracts/`. The coordinate triple, `lab.env` schema and CLI contracts are
  frozen (Article VII). Adding keys to `lab.env` is permitted where FR-6.2 requires it; changing the meaning of an
  existing key is not.
- The deepest-first child rollback logic in `bin/lab-reset`.
- The paired `sql_drop` DDL audit trigger.
- The coordinate resolver's at-or-below rule and its `(high << 32) + low` LSN arithmetic.
- The pull-based evidence architecture: three streams pull from host into VM, one narrow path appends outward.

## 5. Risks

| Risk | Mitigation |
| --- | --- |
| Removing the hatch breaks the legitimate append path | R002 re-proves append and overwrite-refusal before finishing; non-regression section is mandatory |
| Authorised-key regression mechanism leaves stale key material | Mechanism 1 preferred; if 2 is used, destruction asserted in the same invocation (RC-6) |
| Consumer restart loses decoded records | Consumer records last confirmed flush position; slot guarantees replay from there |
| Making slot lag fail closed blocks work during development | Threshold is configurable in `lab.env`; failure names the precondition and the remedy |
| Tier relabelling is read as weakening the suite | It is the opposite, and `spec.md` §2 F-3 states why in terms a reader can follow |
| Live-process test corrupts the data directory | Test asserts no rollback occurred; positive case runs only with the cluster stopped |
