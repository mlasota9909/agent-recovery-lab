"""Shared P5.1 helpers: hashes, headline materiality, frozen-contract table."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from lab_paths import lab_root
from lab_repr import HEADLINE, REPR_IDS
from lab_redaction import pinned  # ADR-M002

F001_HASHES = {
    "representation-interface.md": "57ba586c2d2fcc939f44e63405a5579fa1e2c43653e3ff16457e8375bfd9d5f1",
    "representation-fidelity.md": "3496f0cf876083c91001ab76f32b9029ad033433a2cf7340275a7d6c2f0ca89c",
}
ARTEFACT_HASHES = {
    "R0": "25bff369c36784ae0ba8923f719036ca74b9ba560eddb672c3cba7fecfd64933",
    "R1": "fbf77d349d539e698ef995f3ac602efb086e8a1b7191e951e21cc71b56dc8e88",
    "R2": "0d0ebe449f0c57072ebf7229c926b7dee491c0fc15f3cc469e8b776dd6ec3c86",
}
C001_HASH = "59aeaa61281f211046b953a0641de72dc55c3f6cecc7278ee45802d41003d647"
HEADLINE_DB = "bf21fff2c7c71b39a150d15c9d097c797006139497c51b5a865414433a1ac7dd"
# P5 used strict inequality; WI-G003 names R2 <= 25% of R0 as the materiality bar (stronger, not looser).
MATERIAL_RATIO = 0.25
MODEL_VIEW_KEYSET = (
    "content", "incident_id", "params", "probe_id", "representation", "telemetry",
)

P0_HASHES = {
    "cli.md": "01f0dbc60d7ab5670b8d9b135ab3c8983b9bd00df67e966dd10c36bbc4e5d5d1",
    "coordinate.md": "2080ac9f270aac0f8da718675ac8cb742d009a268fdeb5d634fef03c437c2eef",
    "lab-env.md": "60ba07ae7e308a4923fc829c0f6e0ec568272dc66a8bb94582b4a5953e921e5b",
}
P1_HASHES = {
    "results-row.md": pinned("866edd5677645622669572dfb663a12137a9ca6f1e000f35e7766577b46b0cdf"),
    "results-row.amendment-1.md": "8e99516e5c570d8de94bd4551ce7d1c24961afedab03fcdb19dc85019170f05f",
    "ledger-integrity.md": "15f5740bf4cac9d5fabeabe5b06f1b5656355b0a6a2ba2518218e24dc21d2313",
    "results-row.schema.json": "103eaa92ea48bca7ebcc7ce451b1978d822e92af41dc92b8fbf8f1e7a26d3775",
}
P3_HASHES = {
    "candidate-coordinate.md": "d8795aee07c3379750dc1529bed8311933c0cb2e213da8e9e294593acd17c7f6",
    "arm-coordinate.md": "d2bdef97d8605dab4393b8cf7d69d52f1c196329b4cd6ee15fb27c5e01090947",
}
P4_HASHES = {
    "restore-report.md": pinned("974815821369d1e1477e65851cf0ba39e23e156adf63c5e3840baafa5b30d357"),
    "promotion-gate.md": "edaaeaca69a5b9dbec1172c811b26387b9887f46d8125ab84a29c18442eddfe7",
}


def root() -> Path:
    return Path(os.environ.get("LAB_ROOT") or lab_root())


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def live_artefact_hashes() -> dict[str, str]:
    out = {}
    base = root() / "var" / "repr" / HEADLINE
    for rep in REPR_IDS:
        man = json.loads((base / rep / "manifest.json").read_text(encoding="utf-8"))
        out[rep] = man["content_hash"]
    return out


def artefacts_byte_identical() -> dict:
    live = live_artefact_hashes()
    return {
        "ok": live == ARTEFACT_HASHES,
        "recorded": ARTEFACT_HASHES,
        "live": live,
    }


def headline_material(r0_bytes: int, r2_bytes: int, ratio: float = MATERIAL_RATIO) -> dict:
    strictly_less = r2_bytes < r0_bytes
    material = strictly_less and r2_bytes <= ratio * r0_bytes
    computed_ratio = (r2_bytes / r0_bytes) if r0_bytes else None
    return {
        "R0_evidence_bytes": r0_bytes,
        "R2_evidence_bytes": r2_bytes,
        "delta": r0_bytes - r2_bytes,
        "ratio": computed_ratio,
        "strictly_less": strictly_less,
        "material": material,
        "material_ratio_threshold": ratio,
        "ok": material,
    }


def pb6_headline() -> dict:
    tel = json.loads((root() / "logs/review/F008/telemetry.json").read_text(encoding="utf-8"))
    row = tel["deltas"]["PB-6-candidate-windows"]
    rec = headline_material(int(row["R0"]["evidence_bytes"]), int(row["R2"]["evidence_bytes"]))
    rec["probe_id"] = "PB-6-candidate-windows"
    rec["source"] = "logs/review/F008/telemetry.json"
    rec["R0_tokens"] = row["R0"]["token_estimate"]
    rec["R2_tokens"] = row["R2"]["token_estimate"]
    return rec


def amendment_path() -> Path:
    return root() / "sdd/specs/P5.1-modelview-separation/contracts/representation-interface.amendment-1.md"


def interface_path() -> Path:
    return root() / "sdd/specs/P5-representations/contracts/representation-interface.md"


def frozen_contract_rows() -> list[dict]:
    r = root()
    rows = []

    def add(tranche: str, path: Path, digest: str) -> None:
        got = sha256_file(path)
        rows.append({
            "tranche": tranche, "path": str(path.relative_to(r)),
            "recorded": digest, "live": got, "ok": got == digest,
        })

    p0 = r / "sdd/specs/P0-lab-substrate/contracts"
    for name, digest in P0_HASHES.items():
        add("P0", p0 / name, digest)
    p1c = r / "sdd/specs/P1-ground-truth-harness/contracts"
    add("P1", p1c / "results-row.md", P1_HASHES["results-row.md"])
    add("P1", p1c / "results-row.amendment-1.md", P1_HASHES["results-row.amendment-1.md"])
    add("P1", p1c / "ledger-integrity.md", P1_HASHES["ledger-integrity.md"])
    add("P1", r / "etc/results-row.schema.json", P1_HASHES["results-row.schema.json"])
    add("P2", r / "sdd/specs/P2-capture-collectors/contracts/capture-completeness.md", C001_HASH)
    p3 = r / "sdd/specs/P3-analytics-ranker/contracts"
    for name, digest in P3_HASHES.items():
        add("P3", p3 / name, digest)
    p4 = r / "sdd/specs/P4-restore-validation/contracts"
    for name, digest in P4_HASHES.items():
        add("P4", p4 / name, digest)
    p5 = r / "sdd/specs/P5-representations/contracts"
    for name, digest in F001_HASHES.items():
        add("P5", p5 / name, digest)
    add("headline", r / "evidence/SC-01" / HEADLINE / "db.jsonl", HEADLINE_DB)
    return rows
