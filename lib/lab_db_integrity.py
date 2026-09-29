"""lab-db-integrity: before-images on U/D, DDL via lab_ddl_audit, monotonic LSN."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from lab_paths import current_incident, env, evidence_dir
from lsn import lsn_int

EXIT_ASSERT = 1
EXIT_PRECOND = 2
EXIT_USAGE = 3
INFRA_TABLES = {"lab_heartbeat"}


def die(code: int, msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def emit(obj: dict) -> None:
    print(json.dumps(obj, sort_keys=True))


def load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        die(EXIT_PRECOND, f"precondition failed: ledger missing {path}")
    rows = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            die(EXIT_ASSERT, f"assertion failed: {path}:{lineno} {exc}")
    return rows


def full_identity(rec: dict) -> bool:
    ident = rec.get("identity")
    if not isinstance(ident, list) or not ident:
        return False
    pk = rec.get("pk") or []
    ident_names = {c.get("name") for c in ident if isinstance(c, dict)}
    pk_names = {c.get("name") for c in pk if isinstance(c, dict)}
    if not pk_names:
        return True
    return ident_names > pk_names


def ddl_record(rec: dict) -> dict | None:
    if rec.get("action") != "I" or rec.get("table") != env("DDL_AUDIT_TABLE"):
        return None
    cols = {c["name"]: c.get("value") for c in rec.get("columns") or [] if isinstance(c, dict)}
    if "command_tag" not in cols:
        return None
    return {
        "lsn": rec.get("lsn"),
        "command_tag": cols.get("command_tag"),
        "object_identity": cols.get("object_identity"),
        "principal": cols.get("principal"),
    }


def verify(rows: list[dict], require_ddl: list[tuple[str, str]] | None = None,
           from_lsn: str | None = None, until_lsn: str | None = None) -> dict:
    missing_identity = []
    key_only = []
    decreases = 0
    prev = None
    ddl = []
    ud = 0
    from_n = lsn_int(from_lsn) if from_lsn else None
    until_n = lsn_int(until_lsn) if until_lsn else None
    used = 0
    for i, rec in enumerate(rows):
        action = rec.get("action")
        lsn = rec.get("lsn")
        n = None
        if lsn:
            try:
                n = lsn_int(lsn)
            except ValueError:
                n = None
        if from_n is not None and n is not None and n < from_n:
            continue
        if until_n is not None and n is not None and n >= until_n:
            continue
        used += 1
        # wal2json format-version 2 emits BEGIN with the commit LSN *before*
        # the change LSN. P1 ledger-integrity invariant 3 is on commit (C)
        # records; match that here (C-4).
        if action == "C" and n is not None:
            if prev is not None and n < prev:
                decreases += 1
            prev = n
        if action in {"U", "D"} and rec.get("table") not in INFRA_TABLES:
            ud += 1
            if not rec.get("identity"):
                missing_identity.append(i)
            elif not full_identity(rec):
                key_only.append({"index": i, "table": rec.get("table"), "action": action,
                                 "identity": rec.get("identity"), "pk": rec.get("pk")})
        d = ddl_record(rec)
        if d:
            ddl.append(d)
    ddl_missing = []
    if require_ddl:
        have = {(d["command_tag"], d["object_identity"]) for d in ddl}
        for tag, ident in require_ddl:
            if (tag, ident) not in have:
                ddl_missing.append({"command_tag": tag, "object_identity": ident})
    ok = not missing_identity and not key_only and decreases == 0 and not ddl_missing
    return {
        "ok": ok,
        "records": used,
        "records_file": len(rows),
        "from_lsn": from_lsn,
        "until_lsn": until_lsn,
        "ud_checked": ud,
        "missing_identity": missing_identity[:20],
        "missing_identity_count": len(missing_identity),
        "key_only": key_only[:20],
        "key_only_count": len(key_only),
        "monotonic": decreases == 0,
        "lsn_decreases": decreases,
        "ddl_records": len(ddl),
        "ddl_missing": ddl_missing,
        "changed": False,
    }


def main(argv: list[str]) -> int:
    incident = None
    require: list[tuple[str, str]] = []
    from_lsn = None
    until_lsn = None
    i = 0
    while i < len(argv):
        if argv[i] == "--require-ddl" and i + 2 < len(argv):
            require.append((argv[i + 1], argv[i + 2]))
            i += 3
            continue
        if argv[i] == "--from-lsn" and i + 1 < len(argv):
            from_lsn = argv[i + 1]
            i += 2
            continue
        if argv[i] == "--until-lsn" and i + 1 < len(argv):
            until_lsn = argv[i + 1]
            i += 2
            continue
        if incident is None and not argv[i].startswith("--"):
            incident = argv[i]
            i += 1
            continue
        die(EXIT_USAGE, "usage: lab-db-integrity <incident> [--from-lsn LSN] [--until-lsn LSN] [--require-ddl TAG IDENT]...")
    if incident is None:
        incident = current_incident()
    rows = load_jsonl(evidence_dir(incident) / "db.jsonl")
    report = verify(rows, require or None, from_lsn, until_lsn)
    report["incident"] = incident
    emit(report)
    return 0 if report["ok"] else EXIT_ASSERT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
