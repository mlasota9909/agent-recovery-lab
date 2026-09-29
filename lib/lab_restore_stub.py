"""lab-restore-stub: P4 interface. P1 may only emit verdict stub.

No P1 code path emits a successful recovery verdict that was not earned.
"""
from __future__ import annotations

import json
import sys

EXIT_USAGE = 3


def main(argv: list[str]) -> int:
    incident = None
    i = 0
    while i < len(argv):
        if argv[i] == "--incident" and i + 1 < len(argv):
            incident = argv[i + 1]
            i += 2
            continue
        print("usage: lab-restore-stub --incident <id>", file=sys.stderr)
        return EXIT_USAGE
    if not incident:
        print("usage: lab-restore-stub --incident <id>", file=sys.stderr)
        return EXIT_USAGE
    print(json.dumps({
        "ok": True,
        "changed": False,
        "incident": incident,
        "restore_attempted": False,
        "restore_verdict": "stub",
        "consistency_verdict": "stub",
        "validation_detail": None,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
