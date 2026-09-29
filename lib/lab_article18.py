"""Article XVIII well-formedness: a null is root-caused from primary evidence."""
from __future__ import annotations

from pathlib import Path

REQUIRED_PHRASES = (
    "MUST NOT be reported as a finding",
    "primary evidence",
    "instrument",
    "ruled out",
)


def constitution_path(root: Path) -> Path:
    return root / "sdd" / ".specify" / "memory" / "constitution.md"


def article_headings(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.startswith("## Article ")]


def article_xviii_body(text: str) -> str:
    if "## Article XVIII" not in text:
        return ""
    chunk = text[text.find("## Article XVIII"):]
    nxt = chunk.find("\n## Article ", 3)
    return chunk if nxt < 0 else chunk[:nxt]


def well_formed(text: str) -> dict:
    headings = article_headings(text)
    body = article_xviii_body(text)
    missing = [p for p in REQUIRED_PHRASES if p not in body]
    return {
        "article_count": len(headings),
        "has_xviii": "## Article XVIII" in text,
        "missing_phrases": missing,
        "ok": len(headings) == 18 and "## Article XVIII" in text and not missing,
    }
