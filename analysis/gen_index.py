#!/usr/bin/env python3
"""Generate constitution/ADR index and reject dangling amendment ADR references."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def collect(extra_reference: str | None = None) -> tuple[str, dict]:
    constitution = (ROOT / "sdd/.specify/memory/constitution.md").read_text(encoding="utf-8")
    articles = [line.removeprefix("## ") for line in constitution.splitlines() if line.startswith("## Article ")]
    adr_files = sorted((ROOT / "docs/adr").glob("ADR-*.md"))
    by_token = {re.match(r"(ADR-[A-Za-z0-9.]+-[0-9]+)", path.name).group(1): path for path in adr_files
                if re.match(r"(ADR-[A-Za-z0-9.]+-[0-9]+)", path.name)}
    references = []
    amendment_files = sorted((ROOT / "sdd/specs").glob("*/contracts/*amendment*.md"))
    for path in amendment_files:
        text = path.read_text(encoding="utf-8")
        for token in sorted(set(re.findall(r"ADR-[A-Za-z0-9.]+-[0-9]+", text))):
            references.append({"amendment": str(path.relative_to(ROOT)), "adr": token})
    if extra_reference:
        references.append({"amendment": "scratch/amendment.md", "adr": extra_reference})
    dangling = [row for row in references if row["adr"] not in by_token]
    lines = ["# Governance and ADR index", "", "## Constitutional articles", ""]
    lines.extend(f"- {article}" for article in articles)
    lines += ["", "## Architecture decision records", ""]
    for path in adr_files:
        title = path.read_text(encoding="utf-8").splitlines()[0].removeprefix("# ")
        lines.append(f"- [{title}](adr/{path.name})")
    payload = {"ok": len(articles) == 21 and not dangling, "article_count": len(articles),
               "articles": articles, "adr_count": len(adr_files),
               "adr_files": [str(p.relative_to(ROOT)) for p in adr_files], "amendment_references": references,
               "dangling": dangling}
    return "\n".join(lines) + "\n", payload


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, default=ROOT / "docs/INDEX.md")
    parser.add_argument("--report", type=Path, default=ROOT / "logs/review/M007/index_crosscheck.json")
    parser.add_argument("--inject-missing-adr"); args = parser.parse_args()
    text, payload = collect(args.inject_missing_adr)
    if not args.inject_missing_adr:
        args.output.write_text(text, encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True); args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": payload["ok"], "articles": payload["article_count"], "adrs": payload["adr_count"], "dangling": payload["dangling"]}, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__": raise SystemExit(main())
