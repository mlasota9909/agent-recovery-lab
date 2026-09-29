"""lab-model: pinned LiteLLM invocation with verbatim I/O and containment proof."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from lab_model_runtime import (
    api_key, evaluate_containment, is_sanctioned_endpoint, is_sanctioned_peer,
    load_runtime, start_server, verify_weights,
)
from lab_p3_util import EXIT_ASSERT, EXIT_USAGE, die, write_json

LOOPBACK_PREFIXES = ("127.", "::1", "0:0:0:0:0:0:0:1")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _remote_is_loopback(addr: str) -> bool:
    host = addr.rsplit(":", 1)[0].strip("[]")
    if host.lower().startswith("::ffff:"):
        host = host[7:]
    return host.startswith(LOOPBACK_PREFIXES) or host in {"localhost"}


def outbound_connections(pids: set[int], rec: dict | None = None) -> list[str]:
    """Unsanctioned non-loopback TCP peers of the invocation process."""
    rec = rec or {}
    proc = subprocess.run(["ss", "-tnp"], text=True, capture_output=True, check=False)
    hits = []
    blob = proc.stdout or ""
    pid_needles = [f"pid={p}" for p in pids]
    for line in blob.splitlines():
        if "ESTAB" not in line and "ESTABLISHED" not in line:
            continue
        if pid_needles and not any(n in line for n in pid_needles):
            continue
        cols = line.split()
        peer = cols[4] if len(cols) >= 5 else ""
        if peer and not _remote_is_loopback(peer) and not is_sanctioned_peer(peer, rec):
            hits.append(peer)
    return hits


def invoke(prompt: str, rec: dict | None = None) -> dict:
    rec = rec or load_runtime()
    if not is_sanctioned_endpoint(str(rec.get("endpoint") or ""), rec):
        die(EXIT_ASSERT, "assertion failed: model endpoint is not the pinned LiteLLM gateway")
    dec = rec.get("decoding") or {}
    if int(dec.get("temperature", 1)) != 0:
        die(EXIT_ASSERT, "assertion failed: temperature must be 0")
    verify_weights(rec)
    start_server(rec)
    endpoint = rec["endpoint"].rstrip("/")
    body = {
        "model": rec["model_id"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "top_p": float(dec.get("top_p", 1)),
        "seed": int(dec.get("seed", 42)),
        "max_tokens": int(dec.get("max_tokens", 512)),
        "stream": False,
    }
    payload = json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + api_key(rec),
    }
    req = urllib.request.Request(
        endpoint + "/v1/chat/completions",
        data=payload, headers=headers, method="POST",
    )
    pids = {os.getpid()}
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            raw = resp.read()
    except urllib.error.URLError as exc:
        die(EXIT_ASSERT, f"assertion failed: model invocation failed: {exc}")
    latency_ms = int(round((time.monotonic() - t0) * 1000))
    outbound = outbound_connections(pids, rec)
    containment = evaluate_containment(
        rec["endpoint"], rec["model_id"], rec, observed_peers=outbound,
    )
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        die(EXIT_ASSERT, "assertion failed: model response is not JSON")
    if parsed.get("error"):
        die(EXIT_ASSERT, f"assertion failed: model error: {parsed['error']}")
    choices = parsed.get("choices") or [{}]
    msg = (choices[0].get("message") or {})
    completion = msg.get("content") or ""
    usage = parsed.get("usage") or {}
    prompt_tokens = usage.get("prompt_tokens") or 0
    completion_tokens = usage.get("completion_tokens") or 0
    record = {
        "prompt": prompt,
        "completion": completion,
        "prompt_tokens": int(prompt_tokens),
        "completion_tokens": int(completion_tokens),
        "latency_ms": latency_ms,
        "model_id": rec["model_id"],
        "quantization": rec.get("quantization"),
        "weights_sha256": rec["weights_sha256"],
        "seed": int(dec.get("seed", 42)),
        "temperature": 0,
        "endpoint": rec["endpoint"],
        "outbound_connections": len(outbound),
        "outbound_peers": outbound,
        "offline_verified": containment["offline_verified"],
        "endpoint_host": containment["endpoint_host"],
        "endpoint_is_private": containment["endpoint_is_private"],
        "public_egress_observed": containment["public_egress_observed"],
        "alias_targeted": containment["alias_targeted"],
        "cloud_alias_targeted": containment["cloud_alias_targeted"],
        "weights_hash_matches_pin": containment["weights_hash_matches_pin"],
        "containment_verified": containment["containment_verified"],
        "prompt_sha256": sha256_text(prompt),
        "completion_sha256": sha256_text(str(completion)),
        "served_model": parsed.get("model") or rec["model_id"],
    }
    if not record["containment_verified"]:
        names = ",".join(containment.get("failed_subchecks") or []) or "containment"
        die(EXIT_ASSERT, f"assertion failed: containment {names} "
            f"endpoint_is_private={record['endpoint_is_private']} "
            f"public_egress_observed={record['public_egress_observed']} "
            f"cloud_alias_targeted={record['cloud_alias_targeted']} "
            f"weights_hash_matches_pin={record['weights_hash_matches_pin']}")
    return record


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="lab-model")
    p.add_argument("--prompt-file")
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)
    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    else:
        prompt = sys.stdin.read()
    if not prompt:
        die(EXIT_USAGE, "usage: lab-model [--prompt-file FILE] --out RECORD.json")
    rec = load_runtime()
    record = invoke(prompt, rec)
    write_json(Path(args.out), record)
    print(json.dumps({
        "ok": True, "out": args.out,
        "offline_verified": record["offline_verified"],
        "containment_verified": record["containment_verified"],
        "prompt_tokens": record["prompt_tokens"],
        "latency_ms": record["latency_ms"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
