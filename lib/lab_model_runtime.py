"""Pinned model identity with the gateway location supplied by site configuration."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
from pathlib import Path
from urllib.parse import urlparse

from lab_p3_util import EXIT_ASSERT, EXIT_PRECOND, die
from lab_paths import lab_root

PLACEHOLDER_HASH = "0" * 64
CLOUD_MODEL_IDS = frozenset({
    "deepseek-v4-pro", "gemini-3.5-flash", "glm-5.2", "nemotron-3-ultra-550b",
})
REQUIRED_MODEL_ID = "gb10a-deepseek-v4-flash"
DEFAULT_ENDPOINT = os.environ.get("MODEL_ENDPOINT") or "http://model-gateway:4001"
REQUIRED_LITELLM_PORT = int(os.environ.get("MODEL_LITELLM_PORT") or urlparse(DEFAULT_ENDPOINT).port or 4001)
REQUIRED_LITELLM_NAMES = frozenset({os.environ.get("MODEL_LITELLM_HOST") or urlparse(DEFAULT_ENDPOINT).hostname or "model-gateway"})
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "0.0.0.0", "::"})


def root() -> Path:
    return Path(os.environ.get("LAB_ROOT") or lab_root())


def runtime_path() -> Path:
    env_path = os.environ.get("MODEL_RUNTIME_JSON")
    if env_path:
        return Path(env_path)
    return root() / "var" / "model" / "model-runtime.json"


def api_key_path() -> Path:
    env_path = os.environ.get("MODEL_API_KEY_FILE")
    if env_path:
        return Path(env_path)
    return root() / "var" / "model" / "litellm.key"


def contract_path() -> Path:
    return root() / "sdd/specs/P6-arm-b-model-harness/contracts/model-runtime.md"


def greedy_required(text: str) -> bool:
    compact = text.replace(" ", "")
    return bool(re.search(r"temperature\s*[=:]\s*0(?:\.0+)?(?![.\d])", text) or
                re.search(r"temperature:0(?:\.0+)?(?![.\d])", compact))


def endpoint_host_port(endpoint: str) -> tuple[str, int]:
    parsed = urlparse(endpoint)
    return parsed.hostname or "", parsed.port or (443 if parsed.scheme == "https" else 80)


def normalize_host(host: str) -> str:
    host = (host or "").strip().strip("[]")
    if host.lower().startswith("::ffff:"):
        host = host[7:]
    return host


def _resolve_host(host: str) -> set[str]:
    host = normalize_host(host)
    out = {host} if host else set()
    try:
        ipaddress.ip_address(host)
        return out
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return out
    for info in infos:
        addr = normalize_host(info[4][0])
        if addr:
            out.add(addr)
    return out


def sanctioned_hosts(rec: dict | None = None) -> set[str]:
    del rec
    names = set(REQUIRED_LITELLM_NAMES)
    extra = os.environ.get("MODEL_LITELLM_HOST")
    if extra in REQUIRED_LITELLM_NAMES:
        names.add(extra)
    ips: set[str] = set()
    for name in names:
        ips |= _resolve_host(name)
    return {x for x in ips if x and normalize_host(x) not in LOOPBACK_HOSTS}


def is_sanctioned_endpoint(endpoint: str, rec: dict | None = None) -> bool:
    """True only for the configured LiteLLM host and port. Rec cannot widen the allowlist."""
    del rec
    got_host, got_port = endpoint_host_port(endpoint)
    got_host = normalize_host(got_host)
    if got_port != REQUIRED_LITELLM_PORT:
        return False
    if not got_host or got_host in LOOPBACK_HOSTS:
        return False
    return got_host in sanctioned_hosts() or got_host in REQUIRED_LITELLM_NAMES


def is_sanctioned_peer(peer: str, rec: dict | None = None) -> bool:
    del rec
    host = normalize_host(peer.rsplit(":", 1)[0])
    try:
        port = int(peer.rsplit(":", 1)[1])
    except (IndexError, ValueError):
        port = -1
    if port != REQUIRED_LITELLM_PORT:
        return False
    return host in sanctioned_hosts() or host in REQUIRED_LITELLM_NAMES


def load_runtime() -> dict:
    path = runtime_path()
    if not path.is_file():
        die(EXIT_PRECOND, f"precondition failed: {path} missing")
    rec = json.loads(path.read_text(encoding="utf-8"))
    dec = rec.get("decoding") or {}
    model_id = str(rec.get("model_id") or "")
    if model_id != REQUIRED_MODEL_ID:
        die(EXIT_ASSERT, f"assertion failed: model_id must be {REQUIRED_MODEL_ID}, got {model_id!r}")
    if model_id in CLOUD_MODEL_IDS:
        die(EXIT_ASSERT, "assertion failed: cloud/public-API model id is refused")
    endpoint = str(rec.get("endpoint") or "")
    if not is_sanctioned_endpoint(endpoint, rec):
        die(EXIT_ASSERT, f"assertion failed: model endpoint is not the pinned LiteLLM gateway: {endpoint}")
    if int(dec.get("temperature", 1)) != 0:
        die(EXIT_ASSERT, "assertion failed: temperature must be 0")
    digest = str(rec.get("weights_sha256") or "")
    if not digest or digest == PLACEHOLDER_HASH or len(digest) != 64:
        die(EXIT_ASSERT, "assertion failed: weights_sha256 is unset or placeholder")
    return rec


def api_key(rec: dict | None = None) -> str:
    env_key = os.environ.get("MODEL_API_KEY")
    if env_key:
        return env_key
    path = api_key_path()
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    die(EXIT_PRECOND, f"precondition failed: LiteLLM key missing ({path})")
    return ""


def weights_manifest_path() -> Path:
    return root() / "var" / "model" / "weights-manifest.txt"


def verify_weights(rec: dict | None = None) -> str:
    rec = rec or load_runtime()
    path = weights_manifest_path()
    if not path.is_file():
        die(EXIT_PRECOND, f"precondition failed: weights manifest missing: {path}")
    got = hashlib.sha256(path.read_bytes()).hexdigest()
    want = rec["weights_sha256"]
    if got != want:
        die(EXIT_ASSERT, f"assertion failed: weights-hash drift: live={got} recorded={want}")
    return got


def server_alive(endpoint: str, timeout: float = 2.0) -> bool:
    host, port = endpoint_host_port(endpoint)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def start_server(rec: dict | None = None) -> dict:
    """No local server and no tunnel. The configured LiteLLM gateway must already be reachable."""
    rec = rec or load_runtime()
    endpoint = rec["endpoint"]
    if not server_alive(endpoint):
        die(EXIT_PRECOND, f"precondition failed: LiteLLM not reachable at {endpoint}")
    return {"changed": False, "endpoint": endpoint, "already": True, "tunnel": False}


def lab_hosts() -> set[str]:
    raw = os.environ.get("LAB_HOSTS") or "localhost,lab-vm"
    names = {h.strip().lower() for h in raw.split(",") if h.strip()}
    names |= {n.lower() for n in REQUIRED_LITELLM_NAMES}
    extra = os.environ.get("MODEL_LITELLM_HOST")
    if extra:
        names.add(extra.strip().lower())
    return names


def private_networks():
    raw = os.environ.get("LAB_PRIVATE_CIDRS") or (
        "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,100.64.0.0/10,fd00::/8,fe80::/10"
    )
    nets: list[ipaddress._BaseNetwork] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        nets.append(ipaddress.ip_network(item, strict=False))
    return nets


def forbidden_cloud_alias() -> str:
    return (os.environ.get("LAB_FORBIDDEN_CLOUD_ALIAS") or "deepseek-v4-pro").strip()


def _as_ip(host: str):
    host = normalize_host(host)
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def is_private_ip(host: str) -> bool:
    ip = _as_ip(host)
    if ip is None:
        return False
    if ip.is_private or ip.is_loopback or ip.is_link_local:
        return True
    for net in private_networks():
        if ip in net:
            return True
    return False


def known_lab_ips() -> set[str]:
    ips: set[str] = set()
    for name in lab_hosts():
        for addr in _resolve_host(name):
            if _as_ip(addr) is not None:
                ips.add(normalize_host(addr))
    return ips


def is_lab_private_host(host: str) -> bool:
    """R2a: RFC-1918 / recorded private CIDR / known lab host (name or its resolved address)."""
    host = normalize_host(host)
    if not host:
        return False
    if host.lower() in lab_hosts() or host.lower() in LOOPBACK_HOSTS:
        return True
    if is_private_ip(host):
        return True
    if host in known_lab_ips():
        return True
    ip = _as_ip(host)
    if ip is not None:
        return False
    addrs = [a for a in _resolve_host(host) if _as_ip(a) is not None]
    if not addrs:
        return False
    return all(is_private_ip(a) or a in known_lab_ips() for a in addrs)


def public_peers(peers: list[str]) -> list[str]:
    hits = []
    for peer in peers:
        host = normalize_host(peer.rsplit(":", 1)[0])
        if is_lab_private_host(host) or is_sanctioned_peer(peer, None):
            continue
        if is_private_ip(host):
            continue
        hits.append(peer)
    return hits


def evaluate_containment(
    endpoint: str,
    alias: str,
    rec: dict | None = None,
    observed_peers: list[str] | None = None,
) -> dict:
    rec = rec or {}
    host, _port = endpoint_host_port(endpoint)
    host = normalize_host(host)
    alias = str(alias or "")
    cloud = alias == forbidden_cloud_alias() or alias in CLOUD_MODEL_IDS
    endpoint_is_private = is_lab_private_host(host)
    pub = public_peers(observed_peers or [])
    weights_ok = False
    try:
        verify_weights(rec if rec.get("weights_sha256") else None)
        weights_ok = True
    except SystemExit:
        weights_ok = False
    verified = (
        endpoint_is_private
        and not pub
        and not cloud
        and weights_ok
    )
    failed = []
    if not endpoint_is_private:
        failed.append("R2a endpoint_is_private")
    if pub:
        failed.append("R2b public_egress_observed")
    if cloud:
        failed.append("R2c cloud_alias_targeted")
    if not weights_ok:
        failed.append("R2d weights_hash_matches_pin")
    return {
        "endpoint_host": host,
        "endpoint_is_private": endpoint_is_private,
        "public_egress_observed": bool(pub),
        "public_peers": pub,
        "alias_targeted": alias,
        "cloud_alias_targeted": cloud,
        "weights_hash_matches_pin": weights_ok,
        "containment_verified": verified,
        "offline_verified": verified,
        "failed_subchecks": failed,
    }

