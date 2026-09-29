"""Classify Arm B refusals from verbatim completion bytes. Ignores hand labels."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from lab_p3_util import EXIT_USAGE, die

CAUSES = (
    "grammar-noncompliance",
    "vocabulary-mismatch",
    "explicit-refusal",
    "task-infeasible-claim",
    "other",
)

# P6 R4 rigid form (the extractor that scored H009).
P6_COORD_RE = re.compile(
    r"^COORDINATE:\s*window=(-?\d+)\s+lsn=([0-9A-Fa-f]+/[0-9A-Fa-f]+)\s*$"
)
COORD_LINE_RE = re.compile(r"^COORDINATE:\s*(.*)$")
REFUSAL_LINE_RE = re.compile(r"^REFUSAL:\s*(.*)$")
INFEASIBLE_RE = re.compile(
    r"insufficient|cannot localise|cannot localize|not enough evidence|"
    r"unable to (?:find|determine|localise|localize)|evidence does not",
    re.I,
)
REPR_RE = re.compile(r"\b(R[012])\b")
REPL_RE = re.compile(r"replicate-(\d+)", re.I)


def tagged_lines(completion: str) -> tuple[list[str], list[str]]:
    coords, refusals = [], []
    for raw in completion.splitlines():
        line = raw.strip()
        if COORD_LINE_RE.fullmatch(line):
            coords.append(line)
        elif REFUSAL_LINE_RE.fullmatch(line):
            refusals.append(line)
    return coords, refusals


def classify_bytes(completion: str) -> dict:
    """Exactly one proximate cause from the verbatim completion. Never reads a label file."""
    coords, refusals = tagged_lines(completion)
    final_coord = coords[-1] if coords else None
    final_refusal = refusals[-1] if refusals else None
    final_tagged = final_coord or final_refusal

    if final_refusal and not final_coord:
        reason = REFUSAL_LINE_RE.fullmatch(final_refusal).group(1).strip()  # type: ignore[union-attr]
        return {
            "cause": "explicit-refusal",
            "final_tagged_line": final_refusal,
            "deciding_quote": final_refusal,
            "quoted_in_full": False,
        }

    if final_coord:
        if P6_COORD_RE.fullmatch(final_coord):
            # Grammatically the P6 form; H009 still refused (e.g. window out of range).
            return {
                "cause": "other",
                "final_tagged_line": final_coord,
                "deciding_quote": completion if len(completion) <= 4000 else final_coord,
                "quoted_in_full": True,
            }
        return {
            "cause": "grammar-noncompliance",
            "final_tagged_line": final_coord,
            "deciding_quote": final_coord,
            "quoted_in_full": False,
        }

    if INFEASIBLE_RE.search(completion):
        snippet = completion.strip().splitlines()[-1][:240] if completion.strip() else completion
        return {
            "cause": "task-infeasible-claim",
            "final_tagged_line": final_tagged,
            "deciding_quote": snippet,
            "quoted_in_full": False,
        }

    return {
        "cause": "other",
        "final_tagged_line": final_tagged,
        "deciding_quote": completion,
        "quoted_in_full": True,
    }


def infer_rep_repl(path: Path, completions_dir: Path) -> tuple[str | None, int | None]:
    try:
        rel = path.relative_to(completions_dir)
        parts = list(rel.parts)
    except ValueError:
        parts = list(path.parts)
    rep = None
    for part in parts:
        m = REPR_RE.fullmatch(part)
        if m:
            rep = m.group(1)
            break
    if rep is None:
        m = REPR_RE.search(str(path))
        if m:
            rep = m.group(1)
    repl = None
    m = REPL_RE.search(path.name)
    if m:
        repl = int(m.group(1))
    return rep, repl


def find_completions(completions_dir: Path) -> list[Path]:
    found = sorted(p for p in completions_dir.rglob("*.completion") if p.is_file())
    return found


def diagnose_dir(completions_dir: Path) -> dict:
    if not completions_dir.is_dir():
        die(EXIT_USAGE, f"usage: completions dir missing {completions_dir}")
    rows = []
    for path in find_completions(completions_dir):
        text = path.read_text(encoding="utf-8")
        rec = classify_bytes(text)
        rep, repl = infer_rep_repl(path, completions_dir)
        rows.append({
            "cause": rec["cause"],
            "completion_path": str(path),
            "deciding_quote": rec["deciding_quote"],
            "final_tagged_line": rec["final_tagged_line"],
            "quoted_in_full": rec["quoted_in_full"],
            "replicate": repl,
            "representation": rep,
        })
    rows.sort(key=lambda r: (r["representation"] or "", r["replicate"] if r["replicate"] is not None else -1, r["completion_path"]))
    by_rep: dict[str, dict[str, int]] = {}
    for r in rows:
        rep = r["representation"] or "unknown"
        by_rep.setdefault(rep, {c: 0 for c in CAUSES})
        by_rep[rep][r["cause"]] += 1
        by_rep[rep]["total"] = by_rep[rep].get("total", 0) + 1
    for rep, counts in by_rep.items():
        counts["total"] = sum(counts.get(c, 0) for c in CAUSES)
    return {
        "completions_dir": str(completions_dir),
        "k_expected": 5,
        "n_classified": len(rows),
        "per_completion": rows,
        "per_representation": by_rep,
        "taxonomy": list(CAUSES),
    }


def render_md(payload: dict) -> str:
    lines = [
        "# J001 refusal diagnosis",
        "",
        f"Source: `{payload['completions_dir']}`",
        f"Classified: {payload['n_classified']}",
        "",
        "| Representation | grammar-noncompliance | vocabulary-mismatch | explicit-refusal | task-infeasible-claim | other | total |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for rep in ("R0", "R1", "R2"):
        c = payload["per_representation"].get(rep) or {}
        lines.append(
            f"| {rep} | {c.get('grammar-noncompliance', 0)} | {c.get('vocabulary-mismatch', 0)} | "
            f"{c.get('explicit-refusal', 0)} | {c.get('task-infeasible-claim', 0)} | "
            f"{c.get('other', 0)} | {c.get('total', 0)} |"
        )
    lines += ["", "## Verbatim tagged lines (two quotes for ADR-P6.1-1)", ""]
    quotes = []
    for r in payload["per_completion"]:
        if r["representation"] == "R0" and r["replicate"] == 0:
            quotes.append(r)
        if r["representation"] == "R1" and r["replicate"] == 0:
            quotes.append(r)
        if r["representation"] == "R2" and r["replicate"] == 0:
            quotes.append(r)
    for r in quotes:
        lines.append(f"**{r['representation']} replicate {r['replicate']}** cause=`{r['cause']}`")
        lines.append("")
        lines.append("```")
        lines.append(r["final_tagged_line"] or r["deciding_quote"])
        lines.append("```")
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="lab-diagnose-refusal")
    p.add_argument("completions_dir")
    p.add_argument("--out")
    p.add_argument("--md")
    args = p.parse_args(argv)
    payload = diagnose_dir(Path(args.completions_dir))
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
    if args.md:
        Path(args.md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md).write_text(render_md(payload), encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
