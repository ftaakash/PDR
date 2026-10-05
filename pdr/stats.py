"""
pdr.stats
==========
Repository-clustered estimation shared by the Layer 1 reports. Edges within a
repository are not independent (CLAUDE.md rule 9), so every rate is reported
edge-weighted and repo-weighted, each with a percentile bootstrap CI that
resamples repositories (5,000 resamples, seed 20260928 -- the values the
Layer 1 addendum and scripts/check_claims.py use).
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional

SEED, N_BOOT = 20260928, 5000


def _median(xs: List[float]) -> float:
    s = sorted(xs)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def clustered(by_repo: Dict[str, list], seed: int = SEED, n_boot: int = N_BOOT) -> Optional[dict]:
    """by_repo: repo -> [successes, n] (n > 0). Returns pooled (edge-weighted)
    and macro (repo-weighted) rates in %, each with a repo-clustered percentile
    CI drawn from the same resamples (same RNG sequence as
    scripts/check_claims.clustered_ci, so the Layer 1 figures reproduce)."""
    repos = sorted(by_repo)
    if not repos:
        return None
    rng = random.Random(seed)
    pooled, macro = [], []
    for _ in range(n_boot):
        s = [by_repo[repos[rng.randrange(len(repos))]] for _ in repos]
        pooled.append(sum(x[0] for x in s) / sum(x[1] for x in s))
        macro.append(sum(x[0] / x[1] for x in s) / len(s))
    pooled.sort()
    macro.sort()
    lo, hi = int(.025 * (n_boot - 1)), int(.975 * (n_boot - 1))
    tot_s, tot_n = sum(v[0] for v in by_repo.values()), sum(v[1] for v in by_repo.values())
    rates = [v[0] / v[1] for v in by_repo.values()]
    return {
        "successes": tot_s, "n": tot_n, "n_repos": len(repos),
        "edge_weighted_pct": round(100 * tot_s / tot_n, 2),
        "edge_weighted_ci95_pct": [round(100 * pooled[lo], 1), round(100 * pooled[hi], 1)],
        "repo_weighted_pct": round(100 * sum(rates) / len(rates), 1),
        "repo_weighted_ci95_pct": [round(100 * macro[lo], 1), round(100 * macro[hi], 1)],
        "repo_weighted_median_pct": round(100 * _median(rates), 1),
    }


def ok_within_ripple(row: dict, k: int) -> bool:
    """Ripple-size sensitivity (TASKS.md T2, thresholds declared there before
    computing): a Layer 1 candidate counts as OK at tolerance k if it is OK, or
    if it is RIPPLE with the candidate actually applied and at most k OTHER
    top-level packages changing version. PEER_CONFLICT / RESOLUTION_FAIL /
    TIMEOUT never count. k = 0 reproduces the frozen definition exactly."""
    if row["outcome"] == "OK":
        return True
    return (row["outcome"] == "RIPPLE" and bool(row.get("candidate_actually_applied"))
            and row.get("n_ripple") is not None and row["n_ripple"] <= k)
