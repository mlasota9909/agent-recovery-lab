#!/usr/bin/env python3
"""SC-04 precision/recall + earliest-bounded-commit harness."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from lab_p3_util import EXIT_ASSERT, EXIT_USAGE, die, write_json
from lab_paths import lab_root
from lab_sc04 import score_identified


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        die(EXIT_USAGE, "usage: score.py <groundtruth.json> <identified.json>")
    gt = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    ident = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    truth = gt.get("malicious_set") or gt
    pred = ident.get("malicious_set") or ident.get("identified") or ident
    if not isinstance(truth, list) or not isinstance(pred, list):
        die(EXIT_ASSERT, "assertion failed: expected lists of {row_id,xid}")
    rec = score_identified(truth, pred)
    # Re-derive from the committed ground-truth file, never from a caller-supplied
    # "this is ground truth" label on the identified set.
    print(json.dumps({"ok": True, **rec}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
