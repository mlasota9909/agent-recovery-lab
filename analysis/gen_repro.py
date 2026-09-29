#!/usr/bin/env python3
"""Generate the P8 reproducibility manifest from pinned configuration and source hashes."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from lab_config import load_env
REQUIRED = {
    "model.id", "model.quantisation", "model.weights_sha256", "decoding.seed", "decoding.max_tokens",
    "decoding.context", "producer_commit", "versions.zfs", "versions.postgresql", "versions.host_os",
    "versions.host_kernel", "results.matrix_sha256", "environment.lab_env_sha256",
}


def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()


def env_values() -> dict[str, str]:
    return load_env(ROOT)


def flatten(value: object, prefix: str = "") -> set[str]:
    if not isinstance(value, dict): return {prefix}
    out = set()
    for key, child in value.items(): out |= flatten(child, f"{prefix}.{key}" if prefix else key)
    return out


def validate(payload: dict) -> tuple[bool, list[str]]:
    missing = sorted(REQUIRED - flatten(payload))
    return not missing, missing


def build(commit: str) -> dict:
    env = env_values()
    return {
        "schema_version": 1,
        "model": {"id": env["MODEL_ID"], "quantisation": env["MODEL_QUANT"], "weights_sha256": env["MODEL_WEIGHTS_SHA256"],
                  "runtime": env["MODEL_RUNTIME"], "endpoint_topology": env["MODEL_ENDPOINT"]},
        "decoding": {"seed": int(env["MODEL_SEED"]), "max_tokens": int(env["MODEL_MAX_TOKENS"]),
                     "context": int(env["MODEL_CONTEXT"]), "replicates_per_cell": int(env["ARM_B_K"])},
        "producer_commit": commit,
        "versions": {"zfs": env["ZFS_VERSION"], "zfs_kmod": env["ZFS_KMOD_VERSION"],
                     "postgresql": env["PG_SERVER_VERSION"], "host_os": env["HOST_OS"], "host_kernel": env["HOST_KERNEL"],
                     "guest_os": env["GUEST_OS"], "guest_kernel": env["GUEST_KERNEL"]},
        "results": {"matrix_path": "results/matrix.jsonl", "matrix_sha256": sha(ROOT / "results/matrix.jsonl"),
                    "schema_sha256": sha(ROOT / "etc/results-row.schema.json")},
        "environment": {"lab_env_path": "etc/lab.env", "lab_env_sha256": sha(ROOT / "etc/lab.env")},
        "analysis_contracts": {
            "analysis_input_sha256": sha(ROOT / "sdd/specs/P8-analysis-and-closeout/contracts/analysis-input.md"),
            "analysis_input_amendment_1_sha256": sha(ROOT / "sdd/specs/P8-analysis-and-closeout/contracts/analysis-input.amendment-1.md"),
            "figure_table_manifest_sha256": sha(ROOT / "sdd/specs/P8-analysis-and-closeout/contracts/figure-table-manifest.md"),
            "figure_table_manifest_amendment_1_sha256": sha(ROOT / "sdd/specs/P8-analysis-and-closeout/contracts/figure-table-manifest.amendment-1.md"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, default=ROOT / "repro/manifest.json")
    parser.add_argument("--check", action="store_true"); args = parser.parse_args()
    if args.check:
        payload = json.loads(args.output.read_text(encoding="utf-8")); ok, missing = validate(payload)
    else:
        status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, check=True).stdout
        if status:
            print("precondition failed: tracked tree must be clean before reproducibility manifest production"); return 2
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip()
        payload = build(commit); ok, missing = validate(payload)
        if ok: args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": ok, "missing": missing, "output": str(args.output)}, sort_keys=True)); return 0 if ok else 1


if __name__ == "__main__": raise SystemExit(main())
