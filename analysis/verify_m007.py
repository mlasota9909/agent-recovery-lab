#!/usr/bin/env python3
"""M007 manifest/index negative checks and backup identity report."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))

from gen_index import collect  # noqa: E402
from gen_repro import validate  # noqa: E402


def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--review-dir", type=Path, default=ROOT / "logs/review/M007")
    args = parser.parse_args(); args.review_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / "repro/manifest.json").read_text(encoding="utf-8")); complete, missing = validate(manifest)
    broken = json.loads(json.dumps(manifest)); del broken["model"]["weights_sha256"]
    broken_ok, broken_missing = validate(broken)
    _text, injected = collect("ADR-P8-999")
    negative = {"ok": not broken_ok and "model.weights_sha256" in broken_missing and not injected["ok"],
                "missing_field_probe": {"accepted": broken_ok, "missing": broken_missing},
                "dangling_adr_probe": {"accepted": injected["ok"], "dangling": injected["dangling"]}}
    dated = sorted((ROOT / "backups").glob("thesis-[0-9]*T[0-9]*Z.md"))
    latest = ROOT / "backups/repomix-latest.md"
    if not dated or not latest.is_file():
        backup = {"ok": False, "error": "neutral dated backup/latest absent"}
    else:
        chosen = dated[-1]; backup = {"ok": sha(chosen) == sha(latest), "dated": str(chosen.relative_to(ROOT)),
                                      "latest": str(latest.relative_to(ROOT)), "dated_sha256": sha(chosen),
                                      "latest_sha256": sha(latest), "bytes": chosen.stat().st_size}
    (args.review_dir / "negative-tests.json").write_text(json.dumps(negative, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.review_dir / "backup_identity.json").write_text(json.dumps(backup, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ok = complete and not missing and negative["ok"] and backup["ok"]
    print(json.dumps({"ok": ok, "manifest_complete": complete, "negative": negative["ok"], "backup": backup["ok"]}, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__": raise SystemExit(main())
