"""E008: whole-of-victim + evidence manifest hasher."""
from __future__ import annotations

import json
import sys

from lab_p4_util import victim_plus_evidence_manifest


def main(argv: list[str]) -> int:
    print(json.dumps(victim_plus_evidence_manifest(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
