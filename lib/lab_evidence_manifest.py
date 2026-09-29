"""Recursive SHA-256 manifest of the evidence root (Article XVI)."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path


def evidence_root() -> Path:
    return Path(os.environ["EVIDENCE_ROOT"])


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def manifest_lines(root: Path | None = None) -> list[str]:
    base = (root or evidence_root()).resolve()
    lines: list[str] = []
    if not base.is_dir():
        return lines
    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(base).as_posix()
        st = path.stat()
        lines.append(f"{sha256_file(path)}  mode={st.st_mode & 0o777:04o}  size={st.st_size}  {rel}")
    return lines


def write_manifest(path: Path, root: Path | None = None) -> list[str]:
    lines = manifest_lines(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return lines


def first_diff(before: list[str], after: list[str]) -> str | None:
    bset = set(before)
    aset = set(after)
    if before == after:
        return None
    for ln in after:
        if ln not in bset:
            return ln.split("  ", 3)[-1] if "  " in ln else ln
    for ln in before:
        if ln not in aset:
            return ln.split("  ", 3)[-1] if "  " in ln else ln
    return "(order or duplicate mismatch)"
