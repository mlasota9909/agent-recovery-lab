"""Build and validate runtime/p9-model-set.json from a pinned 3-alias seed.

Probes each backend for its served-model identity, an immutable model digest, and
a tokenizer fingerprint. Refuses (exit non-zero) a degenerate set: fewer than 3
models, two sharing a tokenizer_id, or fewer than 2 distinct families.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from lab_p3_util import EXIT_ASSERT, EXIT_USAGE, die, write_json
from lab_p9 import (
    P9_DECODING, P9_ENDPOINT, backend_served_digest, host_of, is_cloud_alias,
    is_private_host, load_model_set, model_set_path, p61_baseline_runtime, root,
    tokenizer_fingerprint, validate_model_set,
)

# The operator's confirmed three concrete local aliases on the lab gateway
# (recorded in APPLY-FIRST-README: current ~27B model + one different-family +
# one different-family; the anti-artefact value needs the tokenizers to differ).
SEED = [
    {
        "slot": "M1",
        "alias": "gb10a-deepseek-v4-flash",
        "family": "deepseek",
        "param_class": "~27B (MoE, DeepSeek-V4-Flash)",
        "quantisation": "exl3-k2",
        "served_model": "deepseek-v4-flash-0731-exl3-k2",
        "backend": os.environ.get("P9_BACKEND_M1", ""),
        "is_p61_baseline": True,
    },
    {
        "slot": "M2",
        "alias": "gympc-gemma4-26b",
        "family": "gemma",
        "param_class": "~26B (Gemma-4-26B-A4B-IT, QAT q4)",
        "quantisation": "qat-q4",
        "served_model": "gemma4-26b-a4b-it-qat-q4",
        "backend": os.environ.get("P9_BACKEND_M2", ""),
        "is_p61_baseline": False,
    },
    {
        "slot": "M3",
        "alias": "alienware-qwen38-27b",
        "family": "qwen",
        "param_class": "~27B (Qwen3.8-27B-MTP, NVFP4)",
        "quantisation": "nvfp4",
        "served_model": "qwen38-27b-mtp-nvfp4",
        "backend": os.environ.get("P9_BACKEND_M3", ""),
        "is_p61_baseline": False,
    },
]


def build() -> dict:
    missing = ["P9_BACKEND_" + seed["slot"] for seed in SEED if not seed["backend"]]
    if missing:
        die(EXIT_ASSERT, "precondition failed: configure " + ", ".join(missing) + " in etc/lab.local.env")
    baseline_rt = p61_baseline_runtime()
    models = []
    for seed in SEED:
        m = dict(seed)
        m["backend_host"] = host_of(seed["backend"])
        m["backend_is_private"] = is_private_host(m["backend_host"])
        tok = tokenizer_fingerprint(seed["backend"], seed["served_model"])
        if not tok.get("ok"):
            die(EXIT_ASSERT, f"tokenizer probe failed for {seed['alias']}: {tok.get('error')}")
        m["tokenizer_probe"] = tok
        m["tokenizer_id"] = f"{seed['family']}:{seed['served_model']}:tok{tok['fingerprint']}"
        if seed["is_p61_baseline"]:
            m["weights_sha256"] = baseline_rt["weights_sha256"]
            m["model_digest"] = baseline_rt["weights_sha256"]
            m["model_digest_kind"] = "weights_sha256"
            m["hf_revision"] = baseline_rt.get("hf_revision")
        else:
            dg = backend_served_digest(seed["backend"], seed["served_model"])
            if not dg.get("ok"):
                die(EXIT_ASSERT, f"backend digest failed for {seed['alias']}: {dg.get('error')}")
            m["model_digest"] = dg["model_digest"]
            m["model_digest_kind"] = "backend_immutable_identity"
            m["backend_identity"] = dg["identity"]
        models.append(m)
    return {
        "frozen_at": "N001",
        "endpoint": P9_ENDPOINT,
        "endpoint_topology": (
            f"LiteLLM gateway ({P9_ENDPOINT}) -> per-alias private-lab vLLM backends"
        ),
        "decoding": dict(P9_DECODING),
        "p61_baseline_alias": baseline_rt["litellm_alias"],
        "models": models,
    }


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="lab-p9-modelset")
    p.add_argument("--build", action="store_true", help="probe backends and (re)write the record")
    p.add_argument("--validate", action="store_true", help="validate the existing record")
    p.add_argument("--file", help="validate this record instead of the canonical one (negative tests)")
    p.add_argument("--out", default=str(model_set_path()))
    args = p.parse_args(argv)
    if not (args.build or args.validate):
        die(EXIT_USAGE, "usage: lab-p9-modelset --build | --validate [--file F]")
    if args.build:
        rec = build()
        write_json(Path(args.out), rec)
    elif args.file:
        rec = json.loads(Path(args.file).read_text(encoding="utf-8"))
    else:
        rec = load_model_set()
    report = validate_model_set(rec)
    baseline = [m for m in rec.get("models", []) if m.get("is_p61_baseline")]
    matches_p61 = bool(baseline) and baseline[0]["alias"] == rec.get("p61_baseline_alias")
    report["p61_baseline_alias_matches"] = matches_p61
    print(json.dumps({"ok": report["ok"] and matches_p61, "report": report,
                      "out": args.out}, indent=2, sort_keys=True))
    return 0 if (report["ok"] and matches_p61) else EXIT_ASSERT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
