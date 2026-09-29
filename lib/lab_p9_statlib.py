"""Pure-stdlib statistics for the P9 pre-registered plan.

No numpy / scipy in the lab. Every routine is deterministic given its inputs; the
only randomness (the bootstrap) takes an explicit pinned seed.
"""
from __future__ import annotations

import math
import random
from statistics import mean


# --- chi-square upper tail --------------------------------------------

def _gammq(s: float, x: float) -> float:
    """Regularised UPPER incomplete gamma Q(s, x) = 1 - P(s, x). NR gser/gcf."""
    if x <= 0:
        return 1.0
    gln = math.lgamma(s)
    if x < s + 1.0:
        # series for P(s, x)
        ap = s
        term = 1.0 / s
        total = term
        for _ in range(2000):
            ap += 1.0
            term *= x / ap
            total += term
            if abs(term) < abs(total) * 1e-16:
                break
        p = total * math.exp(-x + s * math.log(x) - gln)
        return 1.0 - p
    # continued fraction for Q(s, x) (Lentz)
    tiny = 1e-300
    b = x + 1.0 - s
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 2000):
        an = -i * (i - s)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-16:
            break
    return math.exp(-x + s * math.log(x) - gln) * h


def chi2_sf(x: float, df: int) -> float:
    """P(X > x) for a chi-square with df degrees of freedom.

    P9 only ever calls this with df=2 (Cochran's Q over 3 representations); the
    df=2 branch is the exact closed form. Other df use the incomplete gamma.
    """
    if x <= 0:
        return 1.0
    if df == 2:
        return math.exp(-x / 2.0)
    return max(0.0, min(1.0, _gammq(df / 2.0, x / 2.0)))


# --- Cochran's Q -----------------------------------------------------

def cochran_q(matrix: list[list[int]]) -> dict:
    """matrix[block][treatment] in {0,1}. Returns Q, df, p."""
    b = len(matrix)
    if b == 0:
        return {"Q": None, "df": 0, "p": None, "blocks": 0, "note": "no blocks"}
    k = len(matrix[0])
    col = [sum(row[j] for row in matrix) for j in range(k)]
    row_sums = [sum(row) for row in matrix]
    grand = sum(col)
    num = (k - 1) * (k * sum(c * c for c in col) - grand * grand)
    den = k * grand - sum(r * r for r in row_sums)
    if den == 0:
        return {"Q": 0.0, "df": k - 1, "p": 1.0, "blocks": b,
                "col_sums": col, "note": "degenerate (all blocks constant)"}
    q = num / den
    return {"Q": q, "df": k - 1, "p": chi2_sf(q, k - 1), "blocks": b, "col_sums": col}


# --- McNemar exact --------------------------------------------------

def _binom_coef(n: int, k: int) -> int:
    return math.comb(n, k)


def mcnemar_exact(b: int, c: int) -> dict:
    """Exact two-sided binomial test on discordant pairs (b, c)."""
    n = b + c
    if n == 0:
        return {"b": b, "c": c, "n_discordant": 0, "p": 1.0, "note": "no discordant pairs"}
    lo = min(b, c)
    tail = sum(_binom_coef(n, i) for i in range(lo + 1)) * (0.5 ** n)
    p = min(1.0, 2.0 * tail)
    return {"b": b, "c": c, "n_discordant": n, "p": p}


# --- Holm-Bonferroni ----------------------------------------------

def holm(pvals: dict[str, float]) -> dict[str, dict]:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    out: dict[str, dict] = {}
    running = 0.0
    for rank, (name, p) in enumerate(items):
        adj = min(1.0, (m - rank) * p)
        adj = max(adj, running)          # enforce monotonic non-decreasing
        running = adj
        out[name] = {"p_raw": p, "p_holm": adj, "reject_at_0.05": adj < 0.05}
    return out


# --- bootstrap CI on a paired rate difference --------------------

def bootstrap_paired_diff(blocks: list[tuple[int, int]], seed: int,
                          n_resamples: int = 10000, alpha: float = 0.05) -> dict:
    """blocks: list of (a, b) binary outcomes paired within a block.
    CI on mean(a) - mean(b) by resampling blocks with replacement."""
    if not blocks:
        return {"point": None, "ci_low": None, "ci_high": None, "n_blocks": 0}
    rng = random.Random(seed)
    n = len(blocks)
    point = mean(a for a, _ in blocks) - mean(b for _, b in blocks)
    diffs = []
    for _ in range(n_resamples):
        sample = [blocks[rng.randrange(n)] for _ in range(n)]
        diffs.append(mean(a for a, _ in sample) - mean(b for _, b in sample))
    diffs.sort()
    lo = diffs[max(0, int((alpha / 2) * n_resamples) - 1)]
    hi = diffs[min(n_resamples - 1, int((1 - alpha / 2) * n_resamples) - 1)]
    return {"point": point, "ci_low": lo, "ci_high": hi, "n_blocks": n,
            "n_resamples": n_resamples, "seed": seed, "alpha": alpha}


# --- Cliff's delta ------------------------------------------------

def cliffs_delta(xs: list[float], ys: list[float]) -> dict:
    if not xs or not ys:
        return {"delta": None, "magnitude": "undefined"}
    gt = lt = 0
    for x in xs:
        for y in ys:
            if x > y:
                gt += 1
            elif x < y:
                lt += 1
    d = (gt - lt) / (len(xs) * len(ys))
    a = abs(d)
    mag = ("negligible" if a < 0.147 else "small" if a < 0.33
           else "medium" if a < 0.474 else "large")
    return {"delta": d, "magnitude": mag}
