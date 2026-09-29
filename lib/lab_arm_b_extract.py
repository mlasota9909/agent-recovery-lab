"""lab-arm-b-extract: resolvable-locator completion -> arm-coordinate or refusal."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from lab_p3_util import (
    ARM_FIELDS, EXIT_ASSERT, EXIT_USAGE, canonical_json, die, validate_arm, write_json,
)
from lab_paths import env, evidence_dir, lab_root
from lab_repr import HEADLINE, load_c5_windows
from lsn import lsn_int, lsn_norm, lsn_text_from_int

COORD_HEAD_RE = re.compile(r"^COORDINATE:\s*(.*)$")
REFUSAL_RE = re.compile(r"^REFUSAL:\s*(.*)$")
WINDOW_RE = re.compile(r"window=(-?\d+)")
LSN_HEX_RE = re.compile(r"lsn=([0-9A-Fa-f]+/[0-9A-Fa-f]+)")
LSN_INT_RE = re.compile(r"lsn=(\d+)(?!/)")
TS_RE = re.compile(r"ts=([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z)")
LOCATOR_TOKEN_RE = re.compile(
    r"window=-?\d+|lsn=[0-9A-Fa-f]+/[0-9A-Fa-f]+|lsn=\d+|ts=[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z"
)


def root() -> Path:
    return Path(os.environ.get("LAB_ROOT") or lab_root())


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_bin(name: str, argv: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    envp = os.environ.copy()
    envp["PYTHONPATH"] = str(root() / "lib") + (os.pathsep + envp["PYTHONPATH"] if envp.get("PYTHONPATH") else "")
    return subprocess.run(
        [str(root() / "bin" / name), *argv],
        cwd=str(root()), text=True, capture_output=True, check=False,
        timeout=timeout, env=envp,
    )


def results_incident_id(archive_incident: str) -> str:
    meta = evidence_dir(archive_incident) / "incident.json"
    if meta.is_file():
        rec = json.loads(meta.read_text(encoding="utf-8"))
        if rec.get("incident_id"):
            return rec["incident_id"]
    from lab_p3_util import results_incident_id as rid
    return rid(archive_incident)


def incident_lsn_range(archive_incident: str) -> tuple[int, int]:
    meta = json.loads((evidence_dir(archive_incident) / "incident.json").read_text(encoding="utf-8"))
    lo = lsn_int(meta["open_coordinate"]["lsn"])
    hi = lsn_int(meta["close_coordinate"]["lsn"])
    return lo, hi


def last_safe_lsn_text(archive_incident: str, window_id: int) -> str:
    """Same rule as lab_repr_query._last_safe: previous window last LSN, else first-1."""
    windows = load_c5_windows(archive_incident)
    ids = {int(w["window_id"]) for w in windows}
    if window_id not in ids:
        raise ValueError(f"window {window_id} out of range")
    prev = [w for w in windows if int(w["window_id"]) < window_id]
    if prev:
        last = max(prev, key=lambda w: int(w["window_id"]))
        return lsn_norm(str(last["lsn_end"]))
    first = next(w for w in windows if int(w["window_id"]) == window_id)
    n = int(first["lsn_start_int"]) - 1
    if n < 0:
        raise ValueError(f"window {window_id} has no prior last-safe LSN")
    return lsn_text_from_int(n)


def tagged_lines(completion: str) -> tuple[list[tuple[int, str]], list[tuple[int, str, re.Match[str]]]]:
    coords, refusals = [], []
    for i, line in enumerate(completion.splitlines()):
        s = line.strip()
        m = COORD_HEAD_RE.fullmatch(s)
        if m:
            coords.append((i, s))
            continue
        m = REFUSAL_RE.fullmatch(s)
        if m:
            refusals.append((i, s, m))
    return coords, refusals


def parse_locators(coord_line: str) -> tuple[dict, str | None]:
    m = COORD_HEAD_RE.fullmatch(coord_line.strip())
    if not m:
        return {}, "not a COORDINATE line"
    rest = m.group(1).strip()
    if not rest:
        return {}, "empty COORDINATE"
    leftover = rest
    for tok in LOCATOR_TOKEN_RE.findall(rest):
        leftover = leftover.replace(tok, " ", 1)
    if leftover.strip():
        return {}, f"unparsable locator residue {leftover.strip()!r}"
    loc: dict = {}
    wm = WINDOW_RE.search(rest)
    if wm:
        loc["window"] = int(wm.group(1))
    hex_m = list(LSN_HEX_RE.finditer(rest))
    int_m = []
    for im in LSN_INT_RE.finditer(rest):
        # skip hex matches that also captured digits before the slash
        start = im.start()
        if any(hm.start() == start for hm in hex_m):
            continue
        int_m.append(im)
    if len(hex_m) + len(int_m) > 1:
        return {}, "multiple lsn locators"
    if hex_m:
        loc["lsn_text"] = hex_m[0].group(1)
        loc["lsn_int"] = lsn_int(hex_m[0].group(1))
    elif int_m:
        loc["lsn_int"] = int(int_m[0].group(1))
        loc["lsn_text"] = lsn_text_from_int(loc["lsn_int"])
    tm = list(TS_RE.finditer(rest))
    if len(tm) > 1:
        return {}, "multiple ts locators"
    if tm:
        loc["ts"] = tm[0].group(1)
    if not loc:
        return {}, "no parsable locator"
    return loc, None


def _host_incident(explicit: str | None = None) -> str | None:
    if os.environ.get("LAB_P7_HOST_COORD") != "1":
        return None
    return explicit or os.environ.get("LAB_P7_HOST_INCIDENT") or None


def resolve_lsn(lsn_text: str, incident: str | None = None) -> dict:
    host = _host_incident(incident)
    if host:
        from lab_snapshot_coord import resolve_lsn_from_manifest
        try:
            rec = resolve_lsn_from_manifest(host, lsn_text)
        except SystemExit as exc:
            raise ValueError(str(exc)) from exc
        rec["lsn_int"] = lsn_int(rec["lsn"])
        rec["lsn_text"] = rec["lsn"]
        return rec
    norm = lsn_norm(lsn_text)
    proc = run_bin("lab-coordinate", ["--lsn", norm])
    if proc.returncode != 0:
        raise ValueError(proc.stderr.strip() or proc.stdout.strip() or "lab-coordinate failed")
    rec = json.loads(proc.stdout)
    rec["lsn_int"] = lsn_int(rec["lsn"])
    rec["lsn_text"] = rec["lsn"]
    return rec


def resolve_time(ts: str, incident: str | None = None) -> dict:
    host = _host_incident(incident)
    if host:
        from lab_snapshot_coord import resolve_time_from_manifest
        try:
            rec = resolve_time_from_manifest(host, ts)
        except SystemExit as exc:
            raise ValueError(str(exc)) from exc
        rec["lsn_int"] = lsn_int(rec["lsn"])
        rec["lsn_text"] = rec["lsn"]
        return rec
    proc = run_bin("lab-coordinate", ["--time", ts])
    if proc.returncode != 0:
        raise ValueError(proc.stderr.strip() or proc.stdout.strip() or "lab-coordinate failed")
    rec = json.loads(proc.stdout)
    rec["lsn_int"] = lsn_int(rec["lsn"])
    rec["lsn_text"] = rec["lsn"]
    return rec


def refusal_record(completion: str, reason: str, tagged: str | None = None) -> dict:
    return {
        "outcome": "refusal",
        "arm_coordinate": None,
        "raw_completion": completion,
        "raw_completion_sha256": sha256_text(completion),
        "refusal_reason": reason,
        "rationale": reason,
        "window": None,
        "tagged_line": tagged,
        "locators": None,
    }


def extract(completion: str, archive_incident: str, representation: str) -> dict:
    coords, refusals = tagged_lines(completion)
    if coords and refusals:
        return refusal_record(completion, "ambiguous: both COORDINATE and REFUSAL present")
    if not coords and not refusals:
        return refusal_record(completion, "absent tagged line")
    if len(coords) > 1:
        return refusal_record(completion, "multiple COORDINATE lines")
    if refusals and not coords:
        line_i, line, m = refusals[-1]
        reason = (m.group(1) or "").strip() or "declared refusal"
        rec = refusal_record(completion, reason, tagged=line)
        rec["rationale"] = reason
        return rec
    line_i, line = coords[0]
    loc, err = parse_locators(line)
    if err:
        return refusal_record(completion, err, tagged=line)
    prefix = "\n".join(completion.splitlines()[:line_i]).rstrip()
    resolved_vals: list[tuple[str, dict]] = []
    try:
        lo, hi = incident_lsn_range(archive_incident)
    except Exception as exc:
        return refusal_record(completion, f"incident range unavailable: {exc}", tagged=line)
    try:
        if "window" in loc:
            lsn_text = last_safe_lsn_text(archive_incident, int(loc["window"]))
            resolved_vals.append(("window", resolve_lsn(lsn_text, archive_incident)))
        if "lsn_text" in loc:
            value = int(loc["lsn_int"])
            if value < lo or value > hi:
                return refusal_record(completion, f"LSN {loc['lsn_text']} out of incident range", tagged=line)
            resolved_vals.append(("lsn", resolve_lsn(loc["lsn_text"], archive_incident)))
        if "ts" in loc:
            resolved_vals.append(("ts", resolve_time(loc["ts"], archive_incident)))
    except ValueError as exc:
        return refusal_record(completion, f"unresolvable locator: {exc}", tagged=line)
    if not resolved_vals:
        return refusal_record(completion, "no parsable locator", tagged=line)
    ints = [int(r["lsn_int"]) for _, r in resolved_vals]
    if len(set(ints)) != 1:
        return refusal_record(completion, "ambiguous: locators resolve inconsistently", tagged=line)
    resolved = resolved_vals[0][1]
    value = int(resolved["lsn_int"])
    if value < lo or value > hi:
        return refusal_record(completion, f"LSN {resolved['lsn_text']} out of incident range", tagged=line)
    model_id = os.environ.get("MODEL_ID") or "gb10a-deepseek-v4-flash"
    arm = {
        "incident_id": results_incident_id(archive_incident),
        "arm": "arm_b",
        "selector_version": model_id,
        "representation": representation,
        "lsn_text": resolved["lsn_text"],
        "lsn_int": value,
        "wall_clock": resolved["wall_clock"],
        "snapshot": resolved["snapshot"],
        "chosen_candidate_id": None,
        "rationale": prefix,
        "selection_inputs": {
            "ledger_view": "views.analysis_view",
            "approx_incident_time": None,
            "incident_time_error_seconds": None,
            "read_injection_log": False,
            "read_oracle_optimum": False,
            "read_provenance": False,
        },
    }
    errors = validate_arm(arm)
    if errors:
        die(EXIT_ASSERT, "assertion failed: extracted arm-coordinate invalid: " + "; ".join(errors))
    missing = [f for f in ARM_FIELDS if f not in arm]
    if missing:
        die(EXIT_ASSERT, f"assertion failed: missing arm fields {missing}")
    return {
        "outcome": "determination",
        "arm_coordinate": arm,
        "raw_completion": completion,
        "raw_completion_sha256": sha256_text(completion),
        "refusal_reason": None,
        "rationale": prefix,
        "window": loc.get("window"),
        "tagged_line": line,
        "locators": loc,
    }


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="lab-arm-b-extract")
    p.add_argument("--completion", required=True)
    p.add_argument("--incident", required=True)
    p.add_argument("--representation", required=True, choices=("R0", "R1", "R2"))
    p.add_argument("--out")
    args = p.parse_args(argv)
    path = Path(args.completion)
    if not path.is_file():
        die(EXIT_USAGE, f"usage: completion file missing {path}")
    completion = path.read_text(encoding="utf-8")
    rec = extract(completion, args.incident, args.representation)
    text = canonical_json(rec)
    if args.out:
        write_json(Path(args.out), rec)
    sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
