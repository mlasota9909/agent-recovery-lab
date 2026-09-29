"""lab-p9-verify-models (N002): make each P9 model a contained, reproducible subject.

Article X + P6.1 model-runtime.amendment-1 (R2a-R2d) is re-checked PER MODEL during
a real inference call -- the P6.1 containment result is not assumed to transfer.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

from lab_p3_util import EXIT_ASSERT, EXIT_USAGE, die, write_json
from lab_p9 import (
    P9_DECODING, P9_ENDPOINT, backend_served_digest, evaluate_containment,
    is_cloud_alias, is_private_host, load_model_set, root,
)
from lab_p9_model import invoke


def _sample_egress_during(fn, pid: int):
    """Run fn() while a background thread samples this process's ESTAB peers."""
    seen: list[str] = []
    stop = threading.Event()

    def loop() -> None:
        while not stop.is_set():
            p = subprocess.run(["ss", "-tnp"], text=True, capture_output=True, check=False)
            for line in (p.stdout or "").splitlines():
                if f"pid={pid}" in line and "ESTAB" in line:
                    cols = line.split()
                    if len(cols) >= 5:
                        seen.append(cols[4])
            time.sleep(0.03)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    try:
        result = fn()
    finally:
        stop.set()
        t.join(timeout=1.0)
    return result, sorted(set(seen))


def verify_one(model: dict) -> dict:
    alias = model["alias"]
    # (a) digest
    if model.get("model_digest_kind") == "weights_sha256":
        digest_kind = "weights_sha256"
        digest = model.get("weights_sha256")
        digest_why = "raw weights hashable on the lab host; H001 pin reused"
    else:
        digest_kind = "backend_immutable_identity"
        dg = backend_served_digest(model["backend"], model["served_model"])
        digest = dg.get("model_digest") if dg.get("ok") else None
        digest_why = ("raw weights not reachable on a different host; digest = sha256 over "
                      "{served-id, HF root/revision, max_model_len} per amendment-1 §5 / WI-N002 1a")

    # (b) containment during a real call + (c) smoke; sample egress concurrently
    import os
    rec, sampled_peers = _sample_egress_during(
        lambda: invoke(alias, "Reply with exactly one word: ok"), os.getpid())
    peers = rec.get("outbound_public_peers") or []
    sampled_public = [peer for peer in sampled_peers if not is_private_host(peer.rsplit(":", 1)[0].strip("[]"))]
    egress_ok = not rec["public_egress_observed"] and not sampled_public
    alias_ok = rec["alias_is_pinned_local"] and not rec["cloud_alias_targeted"]
    decoding_ok = rec["temperature"] == 0 and rec["seed"] == int(P9_DECODING["seed"]) \
        and rec["max_tokens"] == int(P9_DECODING["max_tokens"]) and rec.get("top_p") == P9_DECODING["top_p"]
    smoke_ok = bool((rec.get("completion") or "").strip()) and rec["containment_verified"]
    return {
        "alias": alias,
        "family": model.get("family"),
        "tokenizer_id": model.get("tokenizer_id"),
        "backend": model.get("backend"),
        "backend_host": rec.get("endpoint") and model.get("backend_host"),
        "endpoint": P9_ENDPOINT,
        "model_digest_kind": digest_kind,
        "model_digest": digest,
        "model_digest_why": digest_why,
        "weights_sha256": model.get("weights_sha256"),
        "endpoint_is_private": rec["endpoint_is_private"],
        "public_egress_observed": rec["public_egress_observed"],
        "observed_public_peers_post_call": peers,
        "sampled_estab_peers_during_call": sampled_peers,
        "sampled_public_peers": sampled_public,
        "identity_matches": digest == model.get("model_digest"),
        "egress_ok": egress_ok,
        "alias_ok": alias_ok,
        "decoding_ok": decoding_ok,
        "smoke_ok": smoke_ok,
        "containment_verified": rec["containment_verified"],
        "smoke_completion": (rec.get("completion") or "").strip()[:80],
        "finish_reason": rec.get("finish_reason"),
    }


def negative_cloud_alias() -> dict:
    """Point the containment evaluator at a cloud alias / public address; must refuse."""
    baseline = load_model_set()["models"][0]
    cases = []
    for bad_alias in ("deepseek-v4-pro", "frontier-deepseek-v4-flash", "gemini-3.5-flash"):
        m = dict(baseline)
        m["alias"] = bad_alias
        c = evaluate_containment(m, P9_ENDPOINT, observed_public_peers=[])
        cases.append({"alias": bad_alias, "is_cloud_alias": is_cloud_alias(bad_alias),
                      "containment_verified": c["containment_verified"],
                      "failed_subchecks": c["failed_subchecks"]})
    # public backend address
    m = dict(baseline)
    m["backend_host"] = "integrate.api.nvidia.com"
    m["backend"] = "https://integrate.api.nvidia.com/v1"
    c = evaluate_containment(m, "https://integrate.api.nvidia.com/v1", observed_public_peers=["23.1.2.3:443"])
    cases.append({"alias": "public-endpoint", "containment_verified": c["containment_verified"],
                  "failed_subchecks": c["failed_subchecks"]})
    refused_all = all(not case["containment_verified"] for case in cases)
    return {"ok": refused_all, "cases": cases}


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="lab-p9-verify-models")
    p.add_argument("--out", default=str(root() / "runtime" / "p9-model-verify.json"))
    p.add_argument("--review", default=str(root() / "logs" / "review" / "N002"))
    args = p.parse_args(argv)
    rec = load_model_set()
    per = [verify_one(m) for m in rec.get("models", [])]
    neg = negative_cloud_alias()
    payload = {
        "verified_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "endpoint": P9_ENDPOINT,
        "decoding": dict(P9_DECODING),
        "models": per,
        "all_ok": all(m["egress_ok"] and m["alias_ok"] and m["decoding_ok"]
                      and m["smoke_ok"] and m["model_digest"] for m in per),
        "negative_cloud_alias_refused": neg,
    }
    write_json(Path(args.out), payload)
    review = Path(args.review)
    review.mkdir(parents=True, exist_ok=True)
    write_json(review / "p9-model-verify.json", payload)
    write_json(review / "alias-refusal.json", neg)
    print(json.dumps({"ok": payload["all_ok"] and neg["ok"],
                      "models": [{m["alias"]: m["containment_verified"]} for m in per],
                      "negative_refused": neg["ok"]}, indent=2, sort_keys=True))
    return 0 if (payload["all_ok"] and neg["ok"]) else EXIT_ASSERT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
