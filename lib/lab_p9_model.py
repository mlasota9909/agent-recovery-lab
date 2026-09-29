"""lab-p9-model: guarded, contained, per-model invocation for the P9 sweep.

Same choke point as P6/P6.1 (one assembler, verbatim I/O, containment tested not
assumed) but selects one of the three registered P9 models by alias and targets
the loopback LiteLLM gateway (ADR-P9-2). Does not touch bin/lab-model or
lib/lab_model_runtime.py -- those stay pinned for P6.1 reproduction.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from lab_p3_util import EXIT_ASSERT, EXIT_PRECOND, EXIT_USAGE, die, write_json
from lab_p9 import (
    P9_DECODING, P9_ENDPOINT, evaluate_containment, host_of, is_cloud_alias,
    is_private_host, load_model_set, outbound_public_peers, sha256_text,
)


def api_key() -> str:
    env_key = os.environ.get(os.environ.get("MODEL_API_KEY_VAR") or "MODEL_API_KEY")
    if env_key:
        return env_key
    path = Path(os.environ.get("MODEL_API_KEY_FILE") or "").expanduser()
    if not path.is_file():
        from lab_p9 import root
        path = root() / "var" / "model" / "litellm.key"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    die(EXIT_PRECOND, f"precondition failed: gateway key missing ({path})")
    return ""


def model_entry(alias: str) -> dict:
    rec = load_model_set()
    for m in rec.get("models", []):
        if m.get("alias") == alias:
            return m
    die(EXIT_USAGE, f"usage: {alias!r} is not a registered P9 model alias")
    return {}


def invoke(alias: str, prompt: str) -> dict:
    model = model_entry(alias)
    endpoint = P9_ENDPOINT
    dec = dict(P9_DECODING)
    if int(dec.get("temperature", 1)) != 0:
        die(EXIT_ASSERT, "assertion failed: temperature must be 0 (R4 greedy)")
    # R2a/R2c BEFORE the request leaves: never issue a call that could egress.
    registered = {m.get("alias") for m in load_model_set().get("models", [])}
    if is_cloud_alias(alias) or alias not in registered:
        die(EXIT_ASSERT, f"assertion failed: R2c refused pre-flight: {alias!r} is not a "
            f"pinned local P9 alias (cloud={is_cloud_alias(alias)})")
    endpoint_host = host_of(endpoint)
    if not is_private_host(endpoint_host):
        die(EXIT_ASSERT, f"assertion failed: R2a refused pre-flight: endpoint host {endpoint_host!r} not private")
    if model.get("backend_host") and not is_private_host(model["backend_host"]):
        die(EXIT_ASSERT, f"assertion failed: R2a refused pre-flight: backend {model['backend_host']!r} not private")
    body = {
        "model": alias,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "top_p": float(dec["top_p"]),
        "seed": int(dec["seed"]),
        "max_tokens": int(dec["max_tokens"]),
        "stream": False,
    }
    req = urllib.request.Request(
        endpoint.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key()},
        method="POST",
    )
    pids = {os.getpid()}
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            raw = resp.read()
    except urllib.error.URLError as exc:
        die(EXIT_ASSERT, f"assertion failed: model invocation failed: {exc}")
    latency_ms = int(round((time.monotonic() - t0) * 1000))
    public_peers = outbound_public_peers(pids)
    containment = evaluate_containment(model, endpoint, observed_public_peers=public_peers)
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        die(EXIT_ASSERT, "assertion failed: model response is not JSON")
    if parsed.get("error"):
        die(EXIT_ASSERT, f"assertion failed: model error: {parsed['error']}")
    choice = (parsed.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    completion = msg.get("content") or ""
    reasoning = msg.get("reasoning_content") or (
        (msg.get("provider_specific_fields") or {}).get("reasoning") or "")
    usage = parsed.get("usage") or {}
    record = {
        "prompt": prompt,
        "completion": completion,
        "reasoning_content": reasoning,
        "finish_reason": choice.get("finish_reason"),
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "latency_ms": latency_ms,
        "model_alias": alias,
        "model_family": model.get("family"),
        "tokenizer_id": model.get("tokenizer_id"),
        "param_class": model.get("param_class"),
        "quantization": model.get("quantisation"),
        "model_digest": model.get("model_digest"),
        "model_digest_kind": model.get("model_digest_kind"),
        "weights_sha256": model.get("weights_sha256"),
        "seed": int(dec["seed"]),
        "temperature": 0,
        "top_p": float(dec["top_p"]),
        "max_tokens": int(dec["max_tokens"]),
        "endpoint": endpoint,
        "served_model": parsed.get("model") or model.get("served_model"),
        "outbound_public_peers": public_peers,
        "endpoint_is_private": containment["endpoint_is_private"],
        "public_egress_observed": containment["public_egress_observed"],
        "alias_targeted": containment["alias_targeted"],
        "cloud_alias_targeted": containment["cloud_alias_targeted"],
        "alias_is_pinned_local": containment["alias_is_pinned_local"],
        "weights_hash_matches_pin": containment["weights_hash_matches_pin"],
        "containment_verified": containment["containment_verified"],
        "offline_verified": containment["containment_verified"],
        "prompt_sha256": sha256_text(prompt),
        "completion_sha256": sha256_text(str(completion)),
    }
    if not record["containment_verified"]:
        names = ",".join(containment["failed_subchecks"]) or "containment"
        die(EXIT_ASSERT, f"assertion failed: containment {names} for {alias} "
            f"endpoint_is_private={record['endpoint_is_private']} "
            f"public_egress_observed={record['public_egress_observed']} "
            f"cloud_alias_targeted={record['cloud_alias_targeted']} "
            f"weights_hash_matches_pin={record['weights_hash_matches_pin']}")
    return record


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="lab-p9-model")
    p.add_argument("--alias", required=True)
    p.add_argument("--prompt-file")
    p.add_argument("--out", required=True)
    p.add_argument("--smoke", action="store_true", help="fixed trivial prompt")
    args = p.parse_args(argv)
    if args.smoke:
        prompt = "Reply with exactly one word: ok"
    elif args.prompt_file:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    else:
        prompt = sys.stdin.read()
    if not prompt:
        die(EXIT_USAGE, "usage: lab-p9-model --alias A [--prompt-file F | --smoke] --out R.json")
    record = invoke(args.alias, prompt)
    write_json(Path(args.out), record)
    print(json.dumps({
        "ok": True, "out": args.out, "alias": args.alias,
        "containment_verified": record["containment_verified"],
        "finish_reason": record["finish_reason"],
        "completion_tokens": record["completion_tokens"],
        "latency_ms": record["latency_ms"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
