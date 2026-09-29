"""Numeric PostgreSQL LSN arithmetic. Never string-compare LSNs."""
from __future__ import annotations

import re

_LSN = re.compile(r"^([0-9A-Fa-f]+)/([0-9A-Fa-f]+)$")


def parse_lsn(value: str) -> tuple[str, int]:
    if not isinstance(value, str):
        raise ValueError(f"invalid LSN {value!r}")
    m = _LSN.fullmatch(value.strip())
    if not m:
        raise ValueError(f"invalid LSN {value!r}")
    high = int(m.group(1), 16)
    low = int(m.group(2), 16)
    normalised = f"{high:X}/{low:X}"
    return normalised, (high << 32) + low


def lsn_int(value: str) -> int:
    return parse_lsn(value)[1]


def lsn_norm(value: str) -> str:
    return parse_lsn(value)[0]


def lsn_text_from_int(value: int) -> str:
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"invalid integer LSN {value!r}")
    high = value >> 32
    low = value & 0xFFFFFFFF
    return f"{high:X}/{low:X}"


def lsn_cmp(a: str, b: str) -> int:
    ia, ib = lsn_int(a), lsn_int(b)
    return (ia > ib) - (ia < ib)
