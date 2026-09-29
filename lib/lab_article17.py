"""Article XVII well-formedness: subject-visible surface excludes the answer."""
from __future__ import annotations

from pathlib import Path

REQUIRED_PHRASES = (
    "MUST NOT contain the reference answer",
    "mechanically enforced",
    "guard",
)


def constitution_path(root: Path) -> Path:
    return root / "sdd" / ".specify" / "memory" / "constitution.md"


def article_headings(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.startswith("## Article ")]


def article_xvii_body(text: str) -> str:
    if "## Article XVII" not in text:
        return ""
    chunk = text[text.find("## Article XVII"):]
    nxt = chunk.find("\n## Article ", 3)
    return chunk if nxt < 0 else chunk[:nxt]


def prior_articles(text: str) -> str:
    idx = text.find("## Article XVII")
    return text if idx < 0 else text[:idx]


def well_formed(text: str) -> dict:
    headings = article_headings(text)
    body = article_xvii_body(text)
    missing = [p for p in REQUIRED_PHRASES if p not in body]
    return {
        "article_count": len(headings),
        "has_xvii": "## Article XVII" in text,
        "missing_phrases": missing,
        "ok": len(headings) >= 17 and "## Article XVII" in text and not missing,
    }
