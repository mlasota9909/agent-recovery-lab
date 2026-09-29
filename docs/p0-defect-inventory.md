# P0 defect inventory (before-state)

Captured 2026-08-17 by R001. Quotes are verbatim from the P0 build **before** R002–R006. No repairs in this task.

## Summary

| Finding | Description | Location | Article | Repair | Proof |
| --- | --- | --- | --- | --- | --- |
| F-1 | WAL forced command contains a sentinel-gated evidence-read hatch | `bin/lab-wal-receive:24-36`; driver `bin/lab-isolation-test:187-209` | XII | R002 | RC-1, RC-2, RC-3, RC-5 |
| F-2 | Inactive wal2json slot retained 436278992 bytes; AC-10 still PASS because it only asserts `retention_bounded` | `logs/review/T015/verify-results.json` AC-10; `bin/lab-verify.py:107-116` | VIII | R003 | RC-8..RC-12 |
| F-3 | Nine P0 criteria pass by token search in free-text `acceptance.md` (`"FAIL" not in text`) | `bin/lab-verify.py:35-40` and call sites | XIII | R004 | RC-13..RC-17 |
| F-4 | Reset live-Postgres guard never exercised; `/tmp` noexec skip recorded as deviation | `bin/lab-reset:123-125`; `logs/review/T012/negative-running-cluster.log:8-14` | VIII | R005 | RC-18 |
| F-5 | Stale `${PG_DATA}.pre-zfs` left on guest; exact OS/PG versions not pinned for citation | `logs/review/T003/observations.md:12-13`; `etc/lab.env` (no HOST_OS/GUEST_OS/server-version keys) | VIII | R006 | RC-19, RC-20 |

---

## F-1 — boundary read hatch

**Article XII.** A boundary component must not contain a code path that widens the boundary, regardless of default state. The isolation regression enables the hatch by creating `bin/.t009-regression-read-enabled` and sending magic `SSH_ORIGINAL_COMMAND` values; the receiver then `cat`s a file under `EVIDENCE_ROOT`.

**`bin/lab-wal-receive` lines 24–36 (verbatim):**

```
# T009 enables this host-owned, exact-command escape hatch only while proving
# that its isolation check fails.  Without the flag, the receiver accepts only
# the append command below.
if [[ ${SSH_ORIGINAL_COMMAND:-} == "t009-read-evidence-probe" &&
      -f "$SCRIPT_DIR/.t009-regression-read-enabled" ]]; then
  cat "$EVIDENCE_ROOT/.lab-isolation-probe"
  exit 0
fi
if [[ ${SSH_ORIGINAL_COMMAND:-} == "t009-read-missing-probe" &&
      -f "$SCRIPT_DIR/.t009-regression-read-enabled" ]]; then
  cat "$EVIDENCE_ROOT/.t009-deliberately-nonexistent"
  exit 0
fi
```

**`bin/lab-isolation-test` lines 187–209 (verbatim, the grant that the component reads):**

```
  regression_flag="$SCRIPT_DIR/.t009-regression-read-enabled"
  [[ ! -e $regression_flag ]] ||
    die "$EXIT_PRECOND" "precondition failed: stale regression grant flag exists"
  ...
  : >"$regression_flag"
  chmod 0600 "$regression_flag"
```

Repair: R002 deletes both `t009-*` branches and moves the red phase to host-side mutation the receiver does not read. RC-1 scan; RC-3 enumeration includes `t009-read-evidence-probe`.

---

## F-2 — latent evidence-stream failure passes acceptance

**Article VIII.** A check that cannot fail on the dangerous condition is worthless. AC-10 requires only `retention_bounded is True` and `retained_bytes is not None`; `over_threshold: true` and `active: false` still yield PASS.

**`logs/review/T015/verify-results.json` AC-10 object (verbatim fields):**

```
"id": "AC-10",
"observed": {
  "active": false,
  "over_threshold": true,
  "retained_bytes": 436278992,
  "retention_bounded": true,
  "warn_threshold_bytes": 67108864
},
"result": "PASS"
```

**`logs/review/T015/observations.md` line 3 (verbatim):**

```
- The final AC-10 observation reported bounded retention but an inactive consumer and 436,278,992 retained bytes above the 64 MiB warning threshold. This is observable health information, not an AC-10 failure; start a consumer before P1 capture runs.
```

**`bin/lab-verify.py` lines 107–116 (verbatim):**

```
    rc, out, err = command([str(ROOT / "bin/lab-slot"), "--status"])
    ...
    entries.append(result(
        "AC-10", "bin/lab-slot --status", "bounded retention and reported lag",
        slot, rc == 0 and isinstance(slot, dict) and slot.get("retention_bounded") is True
        and slot.get("retained_bytes") is not None,
    ))
```

Repair: R003 supervised consumer; `lab-slot --check` fail-closed; incident open requires consumer live. RC-8..RC-12.

---

## F-3 — self-attested criteria

**Article XIII.** Result-load-bearing criteria must be tier M. Token-in-prose matching is prohibited even for tier A.

**`bin/lab-verify.py` lines 35–40 (verbatim):**

```
def review_pass(task: str, token: str) -> tuple[bool, str]:
    path = REVIEW / task / "acceptance.md"
    if not path.is_file():
        return False, f"missing {path.relative_to(ROOT)}"
    text = path.read_text(encoding="utf-8")
    return token in text and "FAIL" not in text, f"{path.relative_to(ROOT)}: {token!r}={'present' if token in text else 'absent'}"
```

Call sites that are token-in-prose (nine criteria): AC-2 (`T001`/`DEV_LOCATION`), AC-3 (`T002`/`snapshot < 2s`), AC-4 (`T013`/`AC-4`), AC-5 (`T013`/`AC-5`), AC-6 (`T014`/`AC-6`), AC-7 (`T014`/`AC-7`), AC-8 (`T007`/`Re-send existing WAL name is refused`), AC-9 (`T005`/`incident`), AC-11 (`T008`/`provenance`), AC-14 (`T014`/`AC-14`), AC-17 (`T012`/`AC-17`). Load-bearing among these for the measurements: **AC-6** and **AC-14**.

**`sdd/specs/P0-lab-substrate/COMPLETION.md` lines 7–7 (undifferentiated headline):**

```
`bin/lab-verify` exited 0 with AC-1 through AC-18 all PASS. The complete observed record is `logs/review/T015/verify-results.json`.
```

Repair: R004 delete `review_pass`; tier every criterion; AC-6 and AC-14 live mechanical. RC-13..RC-17.

---

## F-4 — untested reset guard

**Article VIII.** The live-cluster refusal is implemented but the T012 negative never ran it.

**`bin/lab-reset` lines 123–125 (verbatim):**

```
  if [[ $stopped != true ]]; then
    die "precondition failed: PostgreSQL is still running and may hold $PG_DATA" "$EXIT_PRECOND"
  fi
```

**`logs/review/T012/negative-running-cluster.log` lines 8–14 (verbatim):**

```
Running-cluster guard:
  The production path performs `systemctl stop postgresql@18-main`, then polls
  `pgrep -x postgres` before it can issue any `zfs rollback`.
  A scratch-process attempt was not executable because the guest mounts /tmp
  with noexec; no victim rollback was attempted and the cluster remained active.
  This environment limitation is recorded as a deviation rather than claiming
  a forced runtime guard result.
```

Repair: R005 `noexec`-safe live-process test (RC-18). Do not change deepest-first rollback.

---

## F-5 — stale PGDATA copy and unpinned versions

**Article VIII / FR-6.** A leftover data directory can confuse restore; the environment table cannot be generated from `lab.env` with exact versions.

**`logs/review/T003/observations.md` lines 12–13 (verbatim):**

```
## Operator note
`${PG_DATA}.pre-zfs` may be removed manually after review. Agent did not delete it.
```

**`etc/lab.env` as of R001:** has `PG_VERSION=18` and `ZFS_VERSION=2.4.1-1ubuntu5` and `WAL2JSON_VERSION=2.6-3`. Missing exact pins: guest OS release, guest kernel, ZFS kmod vs userland split, PostgreSQL **server** version string, host OS release, host kernel. `HOST_OS`/`GUEST_OS`/`PG_SERVER_VERSION` keys are absent (confirmed by `grep`).

Repair: R006 remove `.pre-zfs` after health check; pin versions; generate `docs/environment.md` from `lab.env`. RC-19, RC-20.

---

## Mapping to P0.1 criteria

| Finding | RC ids |
| --- | --- |
| F-1 | RC-1, RC-2, RC-3, RC-4 (non-regression), RC-5, RC-6, RC-7 |
| F-2 | RC-8, RC-9, RC-10, RC-11, RC-12 |
| F-3 | RC-13, RC-14, RC-15, RC-16, RC-17 |
| F-4 | RC-18 |
| F-5 | RC-19, RC-20 |
| all | RC-21 (R007 full suite) |
