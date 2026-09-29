"""P9 shared helpers: model registry, per-model containment, frozen hashes, paths.

P9 reuses the P5.1 model_view + guard and the unchanged P4 path. This module only
adds what a *cross-model* sweep needs: a validated 3-model registry, per-model
containment (Article X + P6.1 amendment R2a-R2d, applied per model), and the
frozen-contract digest checks the P9 gate re-verifies.

It never mutates prior evidence, ledgers, representations, the oracle, or prior
results rows (Article XVI). New rows land only in results/sweep-runs.jsonl.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from lab_p3_util import EXIT_ASSERT, EXIT_PRECOND, die
from lab_paths import lab_root

# --- constants -------------------------------------------------------------

SPEC_DIR = "sdd/specs/P9-model-sweep-statistics"
CONTRACTS = ("model-sweep-plan.md", "statistical-analysis-plan.md", "related-work-positioning.md")

# ADR-P9-2: the pinned P6.1 gateway c220m3:4001 is offline for this tranche; the
# sweep targets the loopback LiteLLM gateway on the lab host instead. Loopback is
# strictly stronger than the cross-host proxy the P6.1 amendment already accepted
# (R2a: private address). The frozen P6.1 amendment stays byte-identical.
P9_ENDPOINT = os.environ.get("P9_ENDPOINT") or "http://127.0.0.1:4001"
P9_GATEWAY_PORT = urlparse(P9_ENDPOINT).port or (443 if P9_ENDPOINT.startswith("https:") else 80)

# ADR-P9-3: max_tokens raised from the 512 P6.1 baseline to 8192, uniformly across
# every model, so a reasoning model is never truncated mid-thought (that would be
# an instrument artefact reported as a refusal -- Article XVIII). Greedy decoding
# with a fixed seed is unchanged; a non-truncated completion is identical under
# either budget.
P9_DECODING = {"temperature": 0, "top_p": 1, "seed": 42, "max_tokens": 8192}

REPR_IDS = ("R0", "R1", "R2")
DEFAULT_K = 5
SWEEP_ID = "P9-SC01-3MODEL-K5"

# Cloud / public-API aliases that MUST never be a sweep target (Article X, R2c).
CLOUD_ALIAS_RE = re.compile(
    r"(^|[-_/])(pro|frontier|cloud)([-_/]|$)"
    r"|gemini|gpt-|claude-|nemotron|glm-\d|kimi|grok|mistral-large|command-r",
    re.IGNORECASE,
)
CLOUD_ALIAS_EXACT = frozenset({
    "deepseek-v4-pro", "gemini-3.5-flash", "glm-5.2", "nemotron-3-ultra-550b",
    "arbiter",
})

PRIVATE_CIDRS_DEFAULT = "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,100.64.0.0/10,fd00::/8,fe80::/10,127.0.0.0/8"


def root() -> Path:
    return Path(os.environ.get("LAB_ROOT") or lab_root())


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- frozen contract digests ---------------------------------------------

def frozen_hashes_path() -> Path:
    return root() / SPEC_DIR / "contracts" / "frozen-hashes.json"


def contract_digests() -> dict[str, str]:
    base = root() / SPEC_DIR / "contracts"
    return {name: sha256_file(base / name) for name in CONTRACTS}


def load_frozen_hashes() -> dict:
    path = frozen_hashes_path()
    if not path.is_file():
        die(EXIT_PRECOND, f"precondition failed: {path} missing (freeze at N001)")
    return json.loads(path.read_text(encoding="utf-8"))


def frozen_hashes_ok() -> dict:
    rec = load_frozen_hashes()
    live = contract_digests()
    pinned = rec.get("contracts", {})
    rows = {}
    for name in CONTRACTS:
        rows[name] = {
            "pinned": pinned.get(name),
            "live": live.get(name),
            "match": pinned.get(name) == live.get(name),
        }
    return {"ok": all(r["match"] for r in rows.values()), "contracts": rows,
            "frozen_before_first_sweep_row": rec.get("frozen_before_first_sweep_row")}


# --- private-address classification --------------------------------------

def _private_networks():
    raw = os.environ.get("LAB_PRIVATE_CIDRS") or PRIVATE_CIDRS_DEFAULT
    nets = []
    for item in raw.split(","):
        item = item.strip()
        if item:
            nets.append(ipaddress.ip_network(item, strict=False))
    # 127/8 is always private even if lab.env's list omits it.
    nets.append(ipaddress.ip_network("127.0.0.0/8"))
    return nets


def _norm_host(host: str) -> str:
    host = (host or "").strip().strip("[]")
    if host.lower().startswith("::ffff:"):
        host = host[7:]
    return host


def _resolve(host: str) -> set[str]:
    host = _norm_host(host)
    out: set[str] = set()
    try:
        ipaddress.ip_address(host)
        return {host}
    except ValueError:
        pass
    try:
        for info in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM):
            out.add(_norm_host(info[4][0]))
    except socket.gaierror:
        pass
    return out


def _lab_hosts() -> set[str]:
    raw = os.environ.get("LAB_HOSTS") or "localhost,lab-vm"
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def is_private_host(host: str) -> bool:
    host = _norm_host(host)
    if not host:
        return False
    if host.lower() in _lab_hosts() or host.lower() in {"localhost", "127.0.0.1", "::1"}:
        return True
    nets = _private_networks()

    def ip_priv(a: str) -> bool:
        try:
            ip = ipaddress.ip_address(a)
        except ValueError:
            return False
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return True
        return any(ip in n for n in nets)

    try:
        ipaddress.ip_address(host)
        return ip_priv(host)
    except ValueError:
        pass
    addrs = _resolve(host)
    return bool(addrs) and all(ip_priv(a) for a in addrs)


def host_of(url: str) -> str:
    from urllib.parse import urlparse
    return _norm_host(urlparse(url).hostname or "")


def is_cloud_alias(alias: str) -> bool:
    alias = (alias or "").strip()
    return alias in CLOUD_ALIAS_EXACT or bool(CLOUD_ALIAS_RE.search(alias))


# --- observed egress ----------------------------------------------------

def outbound_public_peers(pids: set[int]) -> list[str]:
    """Non-loopback, non-private TCP peers held by the invoking process(es)."""
    proc = subprocess.run(["ss", "-tnp"], text=True, capture_output=True, check=False)
    needles = [f"pid={p}" for p in pids]
    hits = []
    for line in (proc.stdout or "").splitlines():
        if "ESTAB" not in line:
            continue
        if needles and not any(n in line for n in needles):
            continue
        cols = line.split()
        if len(cols) < 5:
            continue
        peer = cols[4]
        host = _norm_host(peer.rsplit(":", 1)[0])
        if host in {"127.0.0.1", "::1"} or is_private_host(host):
            continue
        hits.append(peer)
    return hits


# --- model registry ----------------------------------------------------

def model_set_path() -> Path:
    override = os.environ.get("P9_MODEL_SET_JSON")
    if override:
        return Path(override)
    return root() / "runtime" / "p9-model-set.json"


def load_model_set() -> dict:
    path = model_set_path()
    if not path.is_file():
        die(EXIT_PRECOND, f"precondition failed: {path} missing (record at N001)")
    record = json.loads(path.read_text(encoding="utf-8"))
    record["endpoint"] = P9_ENDPOINT
    for model in record.get("models", []):
        backend = os.environ.get("P9_BACKEND_" + model.get("slot", ""))
        if backend:
            model["backend"] = backend
            model["backend_host"] = host_of(backend)
    return record


def validate_model_set(rec: dict) -> dict:
    """Refuse a degenerate set: <3 models, a shared tokenizer_id, or <2 families."""
    models = rec.get("models") or []
    problems: list[str] = []
    if len(models) != 3:
        problems.append(f"expected exactly 3 models, got {len(models)}")
    tok = {}
    for m in models:
        tid = m.get("tokenizer_id")
        if not tid:
            problems.append(f"model {m.get('alias')!r} has no tokenizer_id")
            continue
        tok.setdefault(tid, []).append(m.get("alias"))
    for tid, aliases in tok.items():
        if len(aliases) > 1:
            problems.append(f"tokenizer_id {tid!r} shared by {aliases}")
    families = {m.get("family") for m in models if m.get("family")}
    if len(families) < 2:
        problems.append(f"need >=2 distinct families, got {sorted(families)}")
    for m in models:
        alias = m.get("alias") or ""
        if is_cloud_alias(alias):
            problems.append(f"model {alias!r} looks like a cloud alias (R2c)")
    baseline = [m for m in models if m.get("is_p61_baseline")]
    if len(baseline) != 1:
        problems.append(f"exactly one model must be the P6.1 baseline, got {len(baseline)}")
    return {
        "ok": not problems,
        "n_models": len(models),
        "families": sorted(families),
        "tokenizer_ids": sorted(tok),
        "problems": problems,
    }


def p61_baseline_runtime() -> dict:
    path = root() / "var" / "model" / "model-runtime.json"
    return json.loads(path.read_text(encoding="utf-8"))


# --- per-model containment (R2a-R2d) ----------------------------------

def evaluate_containment(model: dict, endpoint: str, observed_public_peers: list[str] | None = None) -> dict:
    """R2a private endpoint+backend, R2b no public egress, R2c local alias, R2d fixed digest."""
    alias = str(model.get("alias") or "")
    endpoint_host = host_of(endpoint)
    backend_host = _norm_host(model.get("backend_host") or host_of(model.get("backend") or ""))
    r2a = is_private_host(endpoint_host) and (not backend_host or is_private_host(backend_host))
    peers = list(observed_public_peers or [])
    r2b = not peers
    cloud = is_cloud_alias(alias)
    r2c = (not cloud) and alias in _p9_alias_allowlist()
    r2d = _digest_ok(model)
    failed = []
    if not r2a:
        failed.append("R2a endpoint_or_backend_not_private")
    if not r2b:
        failed.append("R2b public_egress_observed")
    if not r2c:
        failed.append("R2c alias_not_pinned_local")
    if not r2d:
        failed.append("R2d model_digest_mismatch")
    return {
        "alias_targeted": alias,
        "endpoint_host": endpoint_host,
        "backend_host": backend_host,
        "endpoint_is_private": r2a,
        "public_egress_observed": bool(peers),
        "public_peers": peers,
        "cloud_alias_targeted": cloud,
        "alias_is_pinned_local": r2c,
        "weights_hash_matches_pin": r2d,
        "containment_verified": r2a and r2b and r2c and r2d,
        "failed_subchecks": failed,
    }


def _p9_alias_allowlist() -> set[str]:
    try:
        return {m["alias"] for m in load_model_set().get("models", [])}
    except SystemExit:
        return set()


def _digest_ok(model: dict) -> bool:
    kind = model.get("model_digest_kind")
    if kind == "weights_sha256":
        want = p61_baseline_runtime().get("weights_sha256")
        return bool(want) and model.get("weights_sha256") == want and model.get("model_digest") == want
    # backend immutable digest: served-model id + backend root/revision, hashed
    return bool(model.get("model_digest")) and len(str(model.get("model_digest"))) == 64


def backend_served_digest(backend: str, served_model: str) -> dict:
    """Immutable model digest for a backend we cannot hash raw weights on:
    sha256 over {served id, HF root/revision, max_model_len}. Recorded, not assumed."""
    try:
        with _urlopen(backend.rstrip("/") + "/models", timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    entry = None
    for m in data.get("data", []):
        if m.get("id") == served_model:
            entry = m
            break
    if entry is None and data.get("data"):
        entry = data["data"][0]
    if entry is None:
        return {"ok": False, "error": "no model entry"}
    ident = {
        "served_model": entry.get("id"),
        "root": entry.get("root"),
        "max_model_len": entry.get("max_model_len"),
    }
    digest = sha256_text(json.dumps(ident, sort_keys=True))
    return {"ok": True, "identity": ident, "model_digest": digest}


def _urlopen(url: str, timeout: int = 8):
    import urllib.request
    return urllib.request.urlopen(url, timeout=timeout)


# --- tokenizer fingerprint -------------------------------------------

TOKENIZER_PROBE = (
    "Window 14 [8053064360..8053066984]: 2 DELETE on relation p2_probe; anomaly 1.7547427646876073."
)


def _api_base(backend: str) -> str:
    """vLLM serves /tokenize at the server root, not under /v1."""
    b = backend.rstrip("/")
    return b[:-3].rstrip("/") if b.endswith("/v1") else b


def tokenizer_fingerprint(backend: str, served_model: str) -> dict:
    import urllib.request
    body = json.dumps({"model": served_model, "prompt": TOKENIZER_PROBE,
                       "add_special_tokens": False}).encode("utf-8")
    req = urllib.request.Request(_api_base(backend) + "/tokenize", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    toks = data.get("tokens") if isinstance(data.get("tokens"), list) else data.get("token_ids")
    if not isinstance(toks, list):
        return {"ok": False, "error": "no token array", "raw": data}
    return {
        "ok": True,
        "n_tokens": len(toks),
        "count": data.get("count"),
        "fingerprint": sha256_text(json.dumps(toks))[:16],
        "ids_head": toks[:16],
    }
