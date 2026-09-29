"""Pin file-level contracts, actual inputs and model identities before collection."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from lab_fl_inputs import build as build_input
from lab_fl_intervals import Parser
from lab_fl_prompt import assemble
from lab_paths import evidence_dir, lab_root

SPEC = "sdd/specs/P12-file-level-test"
CONTRACTS = ("fl-inputs.md", "fl-prompt.md", "fl-answer-rules.md", "fl-checks.md", "fl-analysis-plan.md")
DECODING = {"temperature": 0, "top_p": 1, "seed": 42, "max_tokens": 8192}
ALIASES = {"gb10a-deepseek-v4-flash", "gympc-gemma4-26b", "alienware-qwen38-27b"}


def freeze(incident: str) -> dict:
    root, directory = lab_root(), evidence_dir(incident)
    destination = root / SPEC / "contracts/frozen-hashes.json"
    if destination.exists():
        raise FileExistsError("frozen-hashes.json exists; refusing overwrite")
    results = root / "results"
    configured = os.environ.get("RESULTS_ROOT")
    for folder in {results, Path(configured) if configured else results}:
        if list(folder.glob("fl-study-runs*")):
            raise ValueError("file study output already exists; cannot freeze after collection")
    files = {f"contract:{name}": root / SPEC / "contracts" / name for name in CONTRACTS}
    files.update({"design:spec": root / SPEC / "spec.md", "design:plan": root / SPEC / "plan.md",
                  "models": root / "runtime/p9-model-set.json"})
    models = json.loads(files["models"].read_text(encoding="utf-8"))
    rows = models["models"]
    if (models.get("template") or models.get("decoding") != DECODING or not models.get("endpoint")
            or len(rows) != 3 or {row["alias"] for row in rows} != ALIASES
            or any(not re.fullmatch(r"[0-9a-fA-F]{64}", row.get("model_digest") or "")
                   or not row.get("tokenizer_id") or not row.get("served_model") for row in rows)):
        raise ValueError("model set must contain the three recorded identities and ADR-11 settings")
    for rep in ("R0", "R1", "R2"):
        expected = build_input(incident, rep)
        folder = directory / "fl-inputs" / rep
        if (json.loads((folder / "model-view.json").read_text(encoding="utf-8")) != expected
                or (folder / "content.txt").read_text(encoding="utf-8") != expected["content"] + "\n"
                or (folder / "prompt.txt").read_text(encoding="utf-8") != assemble(expected)):
            raise ValueError("built input is stale: " + rep)
        for name in ("model-view.json", "content.txt", "prompt.txt"):
            files[f"input:{rep}/{name}"] = folder / name
    records = {}
    for key, path in files.items():
        records[key] = {"path": os.path.relpath(path, root),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    out = {"schema_version": 1, "incident_id": incident,
           "frozen_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
           "files": records, "decoding": DECODING, "planned_units": 45,
           "study_output": "fl-study-runs.jsonl", "study_output_present": False}
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also refuses a concurrent freeze, including a dangling symlink.
    with destination.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(out, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return out


def main(argv=None) -> int:
    parser = Parser(prog="lab-fl-freeze")
    parser.add_argument("incident")
    args = parser.parse_args(argv)
    try:
        out = freeze(args.incident)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("freeze refused: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
