"""Q001 freeze: pin the P10 contract + amendment digests and record the Article XXI
pre-registration anchor. Refuses if any scaling-runs* file already exists."""
from __future__ import annotations

import json
import subprocess
import sys

from lab_p10 import (
    CONTRACT_FILES, analysis_plan_digest, contract_digests, frozen_hashes_path, preregistration_path,
    root, utc,
)


def head() -> str:
    return subprocess.run(["git", "-C", str(root()), "rev-parse", "HEAD"], text=True,
                          capture_output=True, check=True).stdout.strip()


def main(argv: list[str]) -> int:
    existing = sorted((root() / "results").glob("scaling-runs*"))
    if existing:
        print(f"refusing to freeze: data already exists: {[p.name for p in existing]}", file=sys.stderr)
        return 1
    if preregistration_path().is_file() and "--force" not in argv:
        print(f"refusing: {preregistration_path()} already exists (frozen)", file=sys.stderr)
        return 1
    digests = contract_digests(CONTRACT_FILES)
    plan = analysis_plan_digest()
    now = utc()
    rec = {
        "tranche": "P10",
        "frozen_at": "Q001",
        "frozen_utc": now,
        "parent_commit_at_freeze": head(),
        "authority": "Article XV (amend by supersession), Article XXI (pre-registration)",
        "contracts": digests,
        "analysis_plan_files": ["scaling-analysis-plan.md", "scaling-analysis-plan.amendment-1.md"],
        "analysis_plan_digest": plan,
        "frozen_before_first_scaling_row": True,
        "scaling_output_paths": ["results/scaling-runs.jsonl", "results/scaling-runs-detail.jsonl"],
        "scaling_output_exists_at_freeze": False,
        "pinned_in": ["lib/lab_p10.py (frozen_hashes_ok, analysis_plan_digest, prereg_check)",
                      "bin/lab-prereg-check", "bin/lab-p10-sweep (plan-drift refusal)",
                      "bin/lab-p10-stats (plan-drift refusal)", "bin/lab-verify-p10"],
        "note": ("analysis_plan_digest = sha256 over 'name:sha256' lines of the plan and its amendment. "
                 "The freeze commit that adds this file precedes every scaling-runs row."),
    }
    frozen_hashes_path().write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    pre = {
        "tranche": "P10",
        "article": "XXI",
        "preregistered_utc": now,
        "analysis_plan_digest": plan,
        "analysis_plan_files": {n: digests[n] for n in rec["analysis_plan_files"]},
        "scaling_runs_present": False,
        "statement": ("The P10 analysis plan and its amendment are frozen at this timestamp, before any "
                      "results/scaling-runs* file exists. Q005 refuses to run if either changes."),
    }
    preregistration_path().parent.mkdir(parents=True, exist_ok=True)
    preregistration_path().write_text(json.dumps(pre, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"frozen_utc": now, "contracts": digests, "analysis_plan_digest": plan}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
