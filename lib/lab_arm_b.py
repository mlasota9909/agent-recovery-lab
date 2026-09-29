"""lab-arm-b: refusal-aware K-replicate driver. Never re-prompts."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from lab_p3_util import EXIT_ASSERT, EXIT_PRECOND, EXIT_USAGE, die, write_json, write_text
from lab_paths import lab_root

DEFAULT_K = 5


def root() -> Path:
    return Path(os.environ.get("LAB_ROOT") or lab_root())


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run_bin(name: str, argv: list[str], stdin: str | None = None, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root() / "lib") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.run(
        [str(root() / "bin" / name), *argv],
        cwd=str(root()), text=True, capture_output=True, check=False,
        timeout=timeout, env=env, input=stdin,
    )


def arm_b_dir(incident: str, representation: str) -> Path:
    return root() / "var" / "arm_b" / incident / representation


def agreement(records: list[dict]) -> dict:
    determinations = [r for r in records if r.get("outcome") == "determination"]
    refusals = [r for r in records if r.get("outcome") == "refusal"]
    lsn_vals = []
    for r in determinations:
        coord = r.get("arm_coordinate") or {}
        if coord.get("lsn_int") is not None:
            lsn_vals.append(int(coord["lsn_int"]))
    identical = 0.0
    if lsn_vals:
        top = Counter(lsn_vals).most_common(1)[0][1]
        identical = top / len(lsn_vals)
    k = len(records)
    return {
        "k": k,
        "determinations": len(determinations),
        "refusals": len(refusals),
        "refusal_rate": (len(refusals) / k) if k else None,
        "identical_coordinate_rate": identical if lsn_vals else None,
        "lsn_int_counts": dict(Counter(lsn_vals)),
    }


def one_replicate(incident: str, representation: str, dest: Path, r: int) -> dict:
    prompt_path = dest / f"replicate-{r}.prompt"
    completion_path = dest / f"replicate-{r}.completion"
    model_path = dest / f"replicate-{r}.model.json"
    extract_path = dest / f"replicate-{r}.extract.json"
    proc = run_bin("lab-arm-b-prompt", ["--incident", incident, "--representation", representation, "--out", str(prompt_path)])
    if proc.returncode != 0:
        die(EXIT_ASSERT, proc.stderr.strip() or "lab-arm-b-prompt failed")
    proc = run_bin("lab-model", ["--prompt-file", str(prompt_path), "--out", str(model_path)], timeout=900)
    if proc.returncode != 0:
        die(EXIT_ASSERT, proc.stderr.strip() or "lab-model failed")
    model = json.loads(model_path.read_text(encoding="utf-8"))
    write_text(completion_path, model.get("completion") or "")
    proc = run_bin("lab-arm-b-extract", [
        "--completion", str(completion_path),
        "--incident", incident,
        "--representation", representation,
        "--out", str(extract_path),
    ])
    if proc.returncode != 0:
        die(EXIT_ASSERT, proc.stderr.strip() or "lab-arm-b-extract failed")
    extracted = json.loads(extract_path.read_text(encoding="utf-8"))
    rationale = extracted.get("rationale") or ""
    write_text(dest / f"replicate-{r}.rationale.txt", rationale)
    if extracted.get("outcome") == "determination" and extracted.get("arm_coordinate"):
        extracted["arm_coordinate"]["rationale"] = rationale
        write_json(extract_path, extracted)
    row = {
        "incident_id": extracted.get("arm_coordinate", {}).get("incident_id") if extracted.get("arm_coordinate") else None,
        "representation": representation,
        "replicate": r,
        "outcome": extracted["outcome"],
        "arm_coordinate": extracted.get("arm_coordinate"),
        "raw_completion_sha256": extracted["raw_completion_sha256"],
        "prompt_tokens": model.get("prompt_tokens"),
        "completion_tokens": model.get("completion_tokens"),
        "latency_ms": model.get("latency_ms"),
        "score": None,
        "coordinate_error": None,
        "refusal_reason": extracted.get("refusal_reason"),
        "rationale": rationale,
        "model_record": str(model_path),
        "completion_path": str(completion_path),
    }
    write_json(dest / f"replicate-{r}.json", row)
    return row


def run_batch(incident: str, representation: str, k: int, dest: Path | None = None) -> dict:
    canonical_home = arm_b_dir(incident, representation)
    if dest is not None:
        target = dest
        target.mkdir(parents=True, exist_ok=True)
        overwritten = False
    else:
        dest = canonical_home
        dest.mkdir(parents=True, exist_ok=True)
        canonical = dest / "replicates.json"
        if canonical.is_file():
            batch = dest / "runs" / utc_stamp()
            batch.mkdir(parents=True, exist_ok=True)
            target = batch
            overwritten = False
        else:
            target = dest
            overwritten = False
    records = []
    for r in range(k):
        records.append(one_replicate(incident, representation, target, r))
    stats = agreement(records)
    payload = {
        "incident": incident,
        "representation": representation,
        "batch_dir": str(target),
        "overwritten": overwritten,
        "records": records,
        **stats,
    }
    write_json(target / "replicates.json", payload)
    if target == dest:
        pass
    else:
        # leave canonical completions untouched
        payload["canonical_preserved"] = True
        write_json(target / "replicates.json", payload)
    return payload


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="lab-arm-b")
    p.add_argument("--incident", required=True)
    p.add_argument("--representation", required=True, choices=("R0", "R1", "R2"))
    p.add_argument("--replicates", type=int, default=DEFAULT_K)
    p.add_argument("--dest", help="write this batch here; do not overwrite a prior canonical set")
    args = p.parse_args(argv)
    if args.replicates < 1:
        die(EXIT_USAGE, "usage: --replicates K >= 1")
    dest = Path(args.dest) if args.dest else None
    out = run_batch(args.incident, args.representation, args.replicates, dest=dest)
    print(json.dumps({
        "ok": True,
        "changed": True,
        "incident": args.incident,
        "representation": args.representation,
        "k": out["k"],
        "batch_dir": out["batch_dir"],
        "overwritten": out["overwritten"],
        "determinations": out["determinations"],
        "refusals": out["refusals"],
        "identical_coordinate_rate": out["identical_coordinate_rate"],
        "refusal_rate": out["refusal_rate"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
