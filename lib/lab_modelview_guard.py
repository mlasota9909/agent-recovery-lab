"""lab-modelview-guard: refuse a subject view that carries the answer (Article XVII)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from lab_p3_util import EXIT_ASSERT, EXIT_USAGE, die
from lab_repr import token_scan
from lab_repr_modelview import MODEL_VIEW_KEYS

FORBIDDEN_KEYS = frozenset({"answer", "reference"})
COORD_KEYS = frozenset({"candidates", "last_safe_lsn_int", "first_lsn_int", "last_lsn_int"})


def _fail(reason: str) -> None:
    print(reason, file=sys.stderr)
    raise SystemExit(EXIT_ASSERT)


def _walk_keys(obj: object, path: str, skip_string_parse: bool) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{path}.{k}" if path else k
            lk = str(k)
            if lk in FORBIDDEN_KEYS:
                _fail(f"violation: forbidden key {lk!r} at {here}")
            if lk in COORD_KEYS:
                _fail(f"violation: coordinate-answer field {lk!r} at {here}")
            hits = token_scan(lk, roles=True)
            if hits:
                _fail(f"violation: provenance token {hits[0]!r} in key {here}")
            _walk_keys(v, here, skip_string_parse=True)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _walk_keys(item, f"{path}[{i}]", skip_string_parse=True)
    elif isinstance(obj, str):
        hits = token_scan(obj, roles=True)
        if hits:
            _fail(f"violation: provenance token {hits[0]!r} at {path}")
        # Do not parse string values as JSON: content may contain LSN digits / JSONL events.


def guard(obj: object) -> None:
    if not isinstance(obj, dict):
        _fail("violation: model_view is not a JSON object")
    keys = tuple(sorted(obj.keys()))
    expected = tuple(sorted(MODEL_VIEW_KEYS))
    if keys != expected:
        extra = sorted(set(obj) - set(MODEL_VIEW_KEYS))
        missing = sorted(set(MODEL_VIEW_KEYS) - set(obj))
        if extra:
            _fail(f"violation: unexpected key {extra[0]!r}")
        _fail(f"violation: missing key {missing[0]!r}; keys={list(keys)}")
    _walk_keys(obj, "", skip_string_parse=True)


def guard_path(path: Path) -> None:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _fail(f"violation: invalid JSON: {exc}")
    guard(obj)


def main(argv: list[str]) -> int:
    if not argv:
        die(EXIT_USAGE, "usage: lab-modelview-guard <model_view.json>")
    path = Path(argv[0])
    if not path.is_file():
        die(EXIT_USAGE, f"usage: model_view file missing: {path}")
    guard_path(path)
    print(json.dumps({"ok": True, "path": str(path)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
