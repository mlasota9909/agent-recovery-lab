"""Read the same Bash configuration as the entry points; persist only local values."""
from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_env(root: Path = REPO_ROOT) -> dict[str, str]:
    result = subprocess.run(
        ["bash", "-c", 'set -ae; source "$1/etc/lab.env"; env -0', "lab-config", str(root)],
        check=True, capture_output=True,
    )
    return dict(item.decode().split("=", 1) for item in result.stdout.split(b"\0") if item)


def write_local_env(values: dict[str, str], root: Path = REPO_ROOT) -> bool:
    """Update supplied keys, preserving other site settings and comments."""
    if any(not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) for key in values):
        raise ValueError("invalid configuration key")
    path = root / "etc/lab.local.env"
    before = path.read_text() if path.exists() else ""
    pending = {key: str(value) for key, value in values.items()}
    lines = []
    for line in before.splitlines():
        match = re.match(r"(?:export\s+)?([A-Z][A-Z0-9_]*)=", line)
        key = match[1] if match else None
        if key in values:
            if key in pending:
                lines.append(f"{key}={shlex.quote(pending.pop(key))}")
        else:
            lines.append(line)
    lines.extend(f"{key}={shlex.quote(value)}" for key, value in pending.items())
    after = "\n".join(lines) + "\n"
    if after == before:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".env.tmp")
    temporary.write_text(after)
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    return True


def config_snapshot(root: Path = REPO_ROOT) -> str:
    """Render evaluated configuration keys without unrelated process variables."""
    keys = set()
    for name in ("lab.env", "lab.local.env"):
        path = root / "etc" / name
        if path.exists():
            keys.update(re.findall(r"^(?:export\s+)?([A-Z][A-Z0-9_]*)=", path.read_text(), re.M))
    values = load_env(root)
    return "".join(f"{key}={shlex.quote(values[key])}\n" for key in sorted(keys) if key in values)
