"""lab-model-containment: R2a–R2d check. Does not invoke the model."""
from __future__ import annotations

import argparse
import json
import sys

from lab_model_runtime import (
    evaluate_containment, forbidden_cloud_alias, load_runtime,
)
from lab_p3_util import EXIT_ASSERT, EXIT_USAGE, die


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="lab-model-containment")
    p.add_argument("--endpoint", help="override endpoint URL (negative tests)")
    p.add_argument("--alias", help="override targeted alias (negative tests)")
    p.add_argument("--peer", action="append", default=[], help="observed peer host:port")
    p.add_argument("--out")
    args = p.parse_args(argv)
    rec = load_runtime()
    endpoint = args.endpoint or rec["endpoint"]
    alias = args.alias or rec["model_id"]
    result = evaluate_containment(endpoint, alias, rec, observed_peers=list(args.peer))
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        from pathlib import Path
        from lab_p3_util import write_text
        write_text(Path(args.out), text)
    sys.stdout.write(text)
    if not result["containment_verified"]:
        names = ",".join(result["failed_subchecks"]) or "containment"
        die(EXIT_ASSERT, f"assertion failed: containment {names} "
            f"endpoint_is_private={result['endpoint_is_private']} "
            f"public_egress_observed={result['public_egress_observed']} "
            f"cloud_alias_targeted={result['cloud_alias_targeted']} "
            f"weights_hash_matches_pin={result['weights_hash_matches_pin']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
