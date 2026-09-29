"""Shared P3 helpers: scenario config, review bundles, JSONL, lab guards."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from lab_paths import env, evidence_dir, lab_root
from lsn import lsn_int

EXIT_ASSERT = 1
EXIT_PRECOND = 2
EXIT_USAGE = 3

FORBIDDEN_PROVENANCE = ("principal", "session_user", "usename", "uid", "originating_uid", "user_id")
CANDIDATE_FIELDS = (
    "incident_id", "candidate_id", "lsn_text", "lsn_int", "wall_clock", "snapshot",
    "skew_seconds", "skew_rows", "features", "analytics_version",
)
CANDIDATE_FEATURE_FIELDS = (
    "proximity_to_first_suspicious", "data_loss_rows", "consistency_risk",
    "anomaly_score", "ddl_in_window",
)
ARM_FIELDS = (
    "incident_id", "arm", "selector_version", "representation", "lsn_text", "lsn_int",
    "wall_clock", "snapshot", "chosen_candidate_id", "rationale", "selection_inputs",
)
SELECTION_INPUT_FIELDS = (
    "ledger_view", "approx_incident_time", "incident_time_error_seconds",
    "read_injection_log", "read_oracle_optimum", "read_provenance",
)


def die(code: int, msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def load_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        die(EXIT_PRECOND, f"precondition failed: scenario config missing {path}")
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, val = line.split("=", 1)
        out[key.strip()] = val.strip().strip('"')
    return out


def scenario_config() -> dict[str, str]:
    raw = os.environ.get("SC01_SCENARIO_CONFIG") or str(lab_root() / "etc/scenarios/sc01.env")
    cfg = load_dotenv(Path(raw))
    for key, val in cfg.items():
        os.environ.setdefault(key, val)
    return cfg


def scenario_relations() -> set[str]:
    cfg = scenario_config()
    rels = cfg.get("SC01_RELATIONS") or cfg.get("SC01_RELATION") or "p2_probe"
    return {r.strip() for r in rels.split(",") if r.strip()}


def require_lab() -> None:
    for key in ("LAB_ROOT", "VM_SSH", "DB_NAME", "PG_PORT", "ROLE_AGENT", "ROLE_APP"):
        env(key)
    root = lab_root()
    if not (root / "etc" / "lab.env").is_file():
        die(EXIT_PRECOND, "precondition failed: not inside the lab deploy root")


def review_dir(task: str) -> Path:
    path = lab_root() / "logs" / "review" / task
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_text(path: Path, text: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    tmp.replace(path)
    os.chmod(path, mode)


def write_json(path: Path, obj: object, mode: int = 0o644) -> None:
    write_text(path, json.dumps(obj, indent=2, sort_keys=True) + "\n", mode)


def canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict], mode: int = 0o644) -> None:
    text = "".join(canonical_json(r) + "\n" for r in rows)
    write_text(path, text, mode)


def dump_lab_env_snapshot(task: str) -> None:
    src = lab_root() / "etc" / "lab.env"
    dst = review_dir(task) / "lab.env.snapshot"
    shutil.copy2(src, dst)
    os.chmod(dst, 0o644)


def append_command(task: str, line: str) -> None:
    path = review_dir(task) / "commands.log"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line.rstrip() + "\n")
    os.chmod(path, 0o644)


def write_acceptance(task: str, rows: list[dict], extra: str = "") -> None:
    lines = [f"# {task} Acceptance", "", "| ID | Tier | Command | Expected | Observed | Result |",
             "| --- | --- | --- | --- | --- | --- |"]
    for row in rows:
        lines.append(
            f"| {row['id']} | {row['tier']} | `{row['command']}` | {row['expected']} | "
            f"{row['observed']} | {row['result']} |"
        )
    m_pass = sum(1 for r in rows if r["tier"] == "M" and r["result"] == "PASS")
    m_n = sum(1 for r in rows if r["tier"] == "M")
    a_pass = sum(1 for r in rows if r["tier"] == "A" and r["result"] == "PASS")
    a_n = sum(1 for r in rows if r["tier"] == "A")
    lines.append("")
    lines.append(f"TIER M {m_pass}/{m_n} · TIER A {a_pass}/{a_n}")
    if extra:
        lines.append("")
        lines.append(extra.rstrip())
    write_text(review_dir(task) / "acceptance.md", "\n".join(lines) + "\n")


def write_artefacts(task: str, paths: list[Path]) -> None:
    lines = [f"# {task} artefacts", ""]
    for path in paths:
        st = path.stat() if path.exists() else None
        mode = oct(st.st_mode & 0o777) if st else "missing"
        digest = sha256_file(path)[:16] if path.is_file() else "-"
        lines.append(f"- `{path}` mode={mode} sha256={digest}")
    write_text(review_dir(task) / "artefacts.md", "\n".join(lines) + "\n")


def ssh_psql(sql: str, role: str | None = None) -> subprocess.CompletedProcess[str]:
    if role:
        user = env("OS_USER_AGENT") if role == env("ROLE_AGENT") else env("OS_USER_APP")
        cmd = (
            f"sudo -n -u {user} psql -X -qAt -v ON_ERROR_STOP=1 "
            f"-p {env('PG_PORT')} -d {env('DB_NAME')}"
        )
    else:
        cmd = (
            f"sudo -n -u postgres psql -X -qAt -v ON_ERROR_STOP=1 "
            f"-p {env('PG_PORT')} -d {env('DB_NAME')}"
        )
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", env("VM_SSH"), cmd],
        input=sql, text=True, capture_output=True, check=False,
    )


def run_bin(name: str, args: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(lab_root() / "bin" / name), *args],
        cwd=str(lab_root()), text=True, capture_output=True, check=False,
        timeout=timeout, env=os.environ,
    )


def run_json(name: str, args: list[str], timeout: int = 180) -> dict:
    proc = run_bin(name, args, timeout=timeout)
    if proc.returncode != 0:
        die(proc.returncode if proc.returncode in {1, 2, 3} else EXIT_ASSERT,
            f"assertion failed: {name} {' '.join(args)}: {proc.stderr.strip() or proc.stdout.strip()}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        die(EXIT_ASSERT, f"assertion failed: {name} stdout is not JSON: {proc.stdout[:400]}")
        return {}


def point_current(incident: str) -> None:
    root = Path(env("ARCHIVE_ROOT"))
    if not (root / incident).is_dir():
        die(EXIT_PRECOND, f"precondition failed: archive {incident} is absent")
    tmp = root / f".current.{incident}.{os.getpid()}"
    tmp.symlink_to(incident)
    tmp.replace(Path(env("ARCHIVE_CURRENT")))


def extract_json_blocks(markdown: str) -> list[str]:
    blocks = []
    for m in re.finditer(r"```json\s*\n(.*?)```", markdown, re.S):
        blocks.append(m.group(1).strip())
    return blocks


def provenance_in_obj(obj: object) -> list[str]:
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in FORBIDDEN_PROVENANCE:
                found.append(k)
            found.extend(provenance_in_obj(v))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(provenance_in_obj(item))
    return found


def validate_candidate(rec: dict) -> list[str]:
    errors = []
    missing = [f for f in CANDIDATE_FIELDS if f not in rec]
    if missing:
        errors.append(f"missing fields: {missing}")
    extra = [k for k in rec if k not in CANDIDATE_FIELDS]
    if extra:
        errors.append(f"unexpected fields: {extra}")
    errors.extend(f"provenance field {f}" for f in provenance_in_obj(rec))
    if "lsn_int" in rec and not isinstance(rec["lsn_int"], int):
        errors.append("lsn_int is not int")
    if rec.get("lsn_text") and rec.get("lsn_int") is not None:
        if lsn_int(rec["lsn_text"]) != rec["lsn_int"]:
            errors.append("lsn_int does not match lsn_text")
    feats = rec.get("features") or {}
    if isinstance(feats, dict):
        for f in CANDIDATE_FEATURE_FIELDS:
            if f not in feats:
                errors.append(f"missing feature {f}")
    return errors


def validate_arm(rec: dict) -> list[str]:
    errors = []
    missing = [f for f in ARM_FIELDS if f not in rec]
    if missing:
        errors.append(f"missing fields: {missing}")
    extra = [k for k in rec if k not in ARM_FIELDS]
    if extra:
        errors.append(f"unexpected fields: {extra}")
    errors.extend(f"provenance field {f}" for f in provenance_in_obj(rec))
    if rec.get("arm") not in {"arm_a", "naive", "arm_b"}:
        errors.append(f"arm {rec.get('arm')!r} not in contract enum")
    if rec.get("lsn_text") and rec.get("lsn_int") is not None:
        if lsn_int(rec["lsn_text"]) != rec["lsn_int"]:
            errors.append("lsn_int does not match lsn_text")
    inputs = rec.get("selection_inputs") or {}
    if isinstance(inputs, dict):
        for f in SELECTION_INPUT_FIELDS:
            if f not in inputs:
                errors.append(f"missing selection_inputs.{f}")
        for flag in ("read_injection_log", "read_oracle_optimum", "read_provenance"):
            if inputs.get(flag) is True:
                errors.append(f"peek flag {flag} is true")
    return errors


def contract_schema_has_provenance(text: str) -> bool:
    # Schema tables only: a field named as a provenance column.
    for name in FORBIDDEN_PROVENANCE:
        if re.search(rf"\|\s*`?{name}`?\s*\|", text, re.I):
            return True
    return False


def results_incident_id(archive_incident: str) -> str:
    stamp = archive_incident.split("_", 1)[1]
    digest = hashlib.sha256(archive_incident.encode("ascii")).hexdigest()[:6]
    return f"i_{stamp}_{digest}"
