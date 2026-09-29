"""Check every hash in each P12 freeze kept here against the files kept with it."""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def verify(folder):
    frozen = json.loads((folder / "frozen-hashes.json").read_text())
    moved = {"evidence/SC-02/": folder / "evidence", "runtime/p9-model-set.json": folder / "model-set.json"}

    def locate(path):
        for prefix, target in moved.items():
            if path == prefix:
                return target
            if prefix.endswith("/") and path.startswith(prefix):
                return target / path[len(prefix):]
        return ROOT / path

    bad = 0
    for key, entry in sorted(frozen["files"].items()):
        path = locate(entry["path"])
        ok = path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
        bad += not ok
        print(("ok   " if ok else "FAIL ") + folder.name + " " + key)
    rows = [json.loads(line) for line in (folder / "results/fl-study-runs.jsonl").read_text().splitlines() if line]
    print(f"{folder.name}: {len(rows)} study rows; planned {frozen['planned_units']}; incident {frozen['incident_id']}")
    return bad == 0 and len(rows) == frozen["planned_units"]


results = [verify(HERE / name) for name in ("study", "reproduction") if (HERE / name / "frozen-hashes.json").is_file()]
sys.exit(0 if results and all(results) else 1)
