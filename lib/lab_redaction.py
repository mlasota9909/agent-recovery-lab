"""ADR-M002: neutral-wording redaction of frozen contract text and one pinned report line.

Each entry maps the digest a gate pinned or recorded before the redaction to the digest after
it. The redaction changed wording only: no field, rule, value or number. Recorded review logs
keep their original digests; a gate passes any pinned or recorded digest through pinned()
and any recorded manifest entry through manifest_entry() before comparing.
"""
from __future__ import annotations

# path: (pre-redaction sha256, size, redacted sha256, size, mode)
REDACTIONS: dict[str, tuple[str, int, str, int, str]] = {
    "sdd/specs/P1-ground-truth-harness/contracts/results-row.md": (
        "866edd5677645622669572dfb663a12137a9ca6f1e000f35e7766577b46b0cdf", 10478,
        "9a8e2bbb7a4e62313a28f8e0d791e3eb210be9c1cef1d7d8e57ed594a2daf680", 10461, "0644"),
    "sdd/specs/P4-restore-validation/contracts/restore-report.md": (
        "974815821369d1e1477e65851cf0ba39e23e156adf63c5e3840baafa5b30d357", 6835,
        "451ca3028497feaabcaafbc77a162130023ef60edf17c07718a4a9e64556d71d", 6830, "0644"),
    "sdd/specs/P6-arm-b-model-harness/contracts/arm-b-protocol.md": (
        "99368b81220490fdd5a0906d0ef398c2589749508563ed136f8a111f8b9bb31f", 5713,
        "3c22626cec108bbfd8410b19cb8b369203e9f4d9f3160c34cd17c1cdc345f37b", 5723, "0444"),
    "sdd/specs/P7-scenario-matrix/contracts/run-matrix-plan.md": (
        "4665066de522a368126e580db94411a63de768008b2bf40f758a93fb73be840e", 5496,
        "32a2c2572b1cd50ac89733c11959b9a08ea35521ce4a6506a5b4c99feadded30", 5474, "0444"),
    "sdd/specs/P7-scenario-matrix/contracts/scenario-definition.md": (
        "74a9c25f15b42ded29a59e3a24414a8bd9ec8f36bee4314bff768a951f78ef55", 5893,
        "31d8c4a18aa4a9fc52cd2367781b31ac7ca9d03c77a6e7c7bdc6879c4c740855", 5878, "0444"),
    "sdd/specs/P8-analysis-and-closeout/contracts/analysis-input.amendment-1.md": (
        "85448cc6d46839791129b3a29fa4c00ab1bf999f2fc56c842669aac941562459", 1183,
        "0f1e364d7643488558c554d1e5832783a7aabf821465257388f5fec3a8754fa5", 1182, "0664"),
    "sdd/specs/P8-analysis-and-closeout/contracts/figure-table-manifest.md": (
        "e9508ac05f0d66790753080448c14a41345e2328647e035753b3a317e0265361", 1626,
        "1688c65422cdcfc8349a2419bb5efe0eebf0266aa2502bc0a847723a3624f3fd", 1615, "0644"),
    "thesis/analysis/p9-statistics.md": (
        "381f53ee570d1a64308f7bc57c3705e60473f83cd3678a4e7b5dd6ead3f77de3", 4944,
        "93d8fb1edafbf5eeff6b7b6db9da47105aa8cca096bd8a6e7ec80796dc73b8ed", 4945, "0664"),
}

_DIGESTS = {old: new for old, _s, new, _n, _m in REDACTIONS.values()}


def pinned(digest: str) -> str:
    """The digest a pinned or recorded value refers to after ADR-M002 (identity otherwise)."""
    return _DIGESTS.get(digest, digest)


def manifest_entry(path: str, entry: str) -> str:
    """Map a recorded '<sha256> mode=<m> size=<n>' entry for a redacted path (identity otherwise)."""
    r = REDACTIONS.get(path)
    if r and entry == f"{r[0]} mode={r[4]} size={r[1]}":
        return f"{r[2]} mode={r[4]} size={r[3]}"
    return entry
