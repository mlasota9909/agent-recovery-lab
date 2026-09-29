"""Assemble the common file recovery wrapper with one guarded input content."""
from __future__ import annotations

from lab_fl_rules import CONTENT_BEGIN, CONTENT_END, content_from_text, visible_index
from lab_modelview_guard import guard
from lab_paths import lab_root


def render(content: str) -> str:
    if not isinstance(content, str):
        raise ValueError("content must be text")
    if CONTENT_BEGIN in content or CONTENT_END in content:
        raise ValueError("input contains reserved prompt boundary markers")
    visible_index(content)
    template = (lab_root() / "sdd/specs/P12-file-level-test/contracts/fl-prompt.md").read_text(encoding="utf-8")
    if template.count("{content}") != 1:
        raise ValueError("prompt wrapper must interpolate content exactly once")
    if template.count(CONTENT_BEGIN) != 1 or template.count(CONTENT_END) != 1:
        raise ValueError("prompt wrapper must have exactly one evidence block")
    assembled = template.replace("{content}", content)
    if content_from_text(assembled) != content:
        raise ValueError("prompt wrapper must place the exact content inside its evidence block")
    return assembled


def assemble(view: dict) -> str:
    guard(view)
    return render(view["content"])
