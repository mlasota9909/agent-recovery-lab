"""Pinned offline tokenizer for P5 probe telemetry. No model, no network."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from lab_paths import lab_root

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[^\sA-Za-z0-9_]")


def tokenizer_spec() -> dict:
    root = lab_root()
    path = Path(os.environ.get("TOKENIZER_PATH") or str(root / "vendor/tokenizer/lab-ws-punct-1.json"))
    spec = json.loads(path.read_text(encoding="utf-8"))
    name = os.environ.get("TOKENIZER_NAME") or spec["name"]
    version = os.environ.get("TOKENIZER_VERSION") or spec["version"]
    return {
        "name": name,
        "version": str(version),
        "id": f"{name}-{version}",
        "path": str(path),
        "algorithm": spec.get("algorithm"),
    }


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text or "")


def token_estimate(text: str) -> int:
    return len(tokenize(text))


def evidence_bytes(text: str) -> int:
    return len((text or "").encode("utf-8"))


def telemetry_for(content: str, spec: dict | None = None) -> dict:
    spec = spec or tokenizer_spec()
    return {
        "evidence_bytes": evidence_bytes(content),
        "token_estimate": token_estimate(content),
        "tokenizer": spec["id"],
    }


def apply_repr_telemetry(row: dict, telemetry: dict) -> dict:
    """Map interface telemetry onto the frozen results-row fields. Schema unchanged."""
    out = dict(row)
    out["evidence_bytes_presented"] = int(telemetry["evidence_bytes"])
    out["token_count"] = int(telemetry["token_estimate"])
    return out


def main(argv: list[str]) -> int:
    text = argv[0] if argv else sys.stdin.read()
    spec = tokenizer_spec()
    print(json.dumps({"ok": True, **telemetry_for(text, spec), "tokenizer_path": spec["path"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
