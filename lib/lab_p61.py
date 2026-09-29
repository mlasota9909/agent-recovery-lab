"""P6.1 shared hashes and paths."""
from __future__ import annotations

from pathlib import Path

from lab_p51 import sha256_file
from lab_paths import lab_root
from lab_redaction import pinned  # ADR-M002

H001_MODEL_RUNTIME = "9e9a86ef6d74a1de6765890f3e6ef79d4e766e75db6e3f913cf6c5b8c98e82d2"
H001_ARM_B_PROTOCOL = pinned("99368b81220490fdd5a0906d0ef398c2589749508563ed136f8a111f8b9bb31f")
H001_P6_RUNTIME_AMENDMENT = "ee097868a897e1ba52c3dbec042461187824ef5e753a0970dc53369038a500f2"
P51_INTERFACE_AMENDMENT = "fc9e3b162f234821021cc655cf917938570ee66e7b895ab5a37efe5eba34de42"

INCIDENT = "SC-01_20260824T091611Z"
GT_LSN = "1/E1000000"
GT_LSN_INT = 8069840896


def root() -> Path:
    return lab_root()


def p61_contracts() -> Path:
    return root() / "sdd/specs/P6.1-arm-b-answerability/contracts"


def p6_contracts() -> Path:
    return root() / "sdd/specs/P6-arm-b-model-harness/contracts"


def file_hash(path: Path) -> str:
    return sha256_file(path)
