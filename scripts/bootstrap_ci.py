#!/usr/bin/env python3
"""
scripts/bootstrap_ci.py --in results/raw/provenance_phase1/edges.csv --out results/processed/phase1_bootstrap.json

Implements the Phase-0-frozen statistical design (docs/methodology_freeze.md
Section 3): dependency edges within one repository are correlated (they
share a lockfile, a dependency graph, an era of adoption), so a naive
binomial CI computed over 69,692 pooled edges massively overstates precision
-- the effective sample size is closer to the number of REPOSITORIES (45)
than the number of edges. We resample REPOSITORIES with replacement (not
edges), which is the standard cluster bootstrap for this situation.

Primary Phase-1 statistic (frozen before this script was run against the
45-repo data -- see methodology_freeze.md):
    semantic recoverability among deficient edges, pooled within each
    bootstrap resample, with a repository-clustered percentile bootstrap CI.

Secondary Phase-1 statistic (also frozen in advance):
    proportion of repositories that contain at least one recoverable
    (semantic or resolution-preserving) deficient edge, with a Wilson score
    CI (repos ARE the natural independent unit for this one, so no
    bootstrap needed -- a closed-form binomial-proportion CI is correct and
    preferred over resampling when it's available).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import defaultdict

DEFICIENT_STATES = {"DEFICIENT_UNRECOVERABLE", "DEFICIENT_SEMANTIC_ONLY", "DEFICIENT_RESOLUTION_PRESERVING"}
RECOVERABLE_STATES = {"DEFICIENT_SEMANTIC_ONLY", "DEFICIENT_RESOLUTION_PRESERVING"}


def _wilson_ci(successes: int, n: int, z: float = 1.96):
    if n == 0:
        return None, None
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return max(0.0, center - half), min(1.0, center + half)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_csv", required=True)
    ap.add_argument("--out", dest="out_json", required=True)
    ap.add_argument("--n-boot", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=20260924,
                     help="fixed seed for reproducibility -- frozen, not tuned post-hoc")
    args = ap.parse_args()

    by_repo = defaultdict(lambda: {"deficient": 0, "recoverable": 0, "resolution_preserving": 0})
    with open(args.in_csv, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            state = row["state"]
            if state not in DEFICIENT_STATES:
                continue
            r = by_repo[row["repo"]]
            r["deficient"] += 1
            if state in RECOVERABLE_STATES:
                r["recoverable"] += 1
            if state == "DEFICIENT_RESOLUTION_PRESERVING":
                r["resolution_preserving"] += 1

    repos = sorted(by_repo.keys())
    n_repos = len(repos)
    print(f"[bootstrap_ci] {n_repos} repositories with >=1 deficient edge")

    # ---- point estimate (pooled across all repos, no resampling) ----
    total_deficient = sum(r["deficient"] for r in by_repo.values())
    total_recoverable = sum(r["recoverable"] for r in by_repo.values())
    point_estimate = 100.0 * total_recoverable / total_deficient if total_deficient else None

    # ---- primary: repository-clustered percentile bootstrap on pooled recoverability% ----
    rng = random.Random(args.seed)
    boot_estimates = []
    for _ in range(args.n_boot):
        sample_repos = [repos[rng.randrange(n_repos)] for _ in range(n_repos)]
        d = sum(by_repo[r]["deficient"] for r in sample_repos)
        rec = sum(by_repo[r]["recoverable"] for r in sample_repos)
        if d > 0:
            boot_estimates.append(100.0 * rec / d)
    boot_estimates.sort()

    def pct(p):
        idx = int(round(p * (len(boot_estimates) - 1)))
        return boot_estimates[idx]

    ci_low, ci_high = pct(0.025), pct(0.975)

    # ---- secondary: proportion of repos containing >=1 recoverable case, Wilson CI ----
    repos_with_recoverable = sum(1 for r in by_repo.values() if r["recoverable"] > 0)
    repos_with_resolution_preserving = sum(1 for r in by_repo.values() if r["resolution_preserving"] > 0)
    w_low, w_high = _wilson_ci(repos_with_recoverable, n_repos)

    summary = {
        "method": "repository-clustered percentile bootstrap (primary) + Wilson score CI (secondary); "
                  "frozen before running against Phase-1 data per docs/methodology_freeze.md Section 3",
        "n_repos_with_deficient_edges": n_repos,
        "n_bootstrap_resamples": args.n_boot,
        "seed": args.seed,
        "primary_statistic": "semantic_recovery_pct_of_deficient (pooled across repository-resampled edges)",
        "point_estimate_pct": round(point_estimate, 2) if point_estimate is not None else None,
        "bootstrap_ci95_pct": [round(ci_low, 2), round(ci_high, 2)],
        "secondary_statistic": "proportion of repositories containing >=1 recoverable deficient edge",
        "repos_with_recoverable_case": repos_with_recoverable,
        "repos_with_recoverable_case_pct": round(100.0 * repos_with_recoverable / n_repos, 2),
        "repos_with_recoverable_case_wilson_ci95_pct": [
            round(w_low * 100, 2) if w_low is not None else None,
            round(w_high * 100, 2) if w_high is not None else None,
        ],
        "repos_with_resolution_preserving_case": repos_with_resolution_preserving,
        "repos_with_resolution_preserving_case_pct": round(100.0 * repos_with_resolution_preserving / n_repos, 2),
        "per_repo": {
            r: {
                "deficient": v["deficient"],
                "recoverable": v["recoverable"],
                "resolution_preserving": v["resolution_preserving"],
                "recoverable_pct_of_deficient": round(100.0 * v["recoverable"] / v["deficient"], 2) if v["deficient"] else None,
            }
            for r, v in sorted(by_repo.items())
        },
    }

    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"[bootstrap_ci] point estimate: {summary['point_estimate_pct']}%")
    print(f"[bootstrap_ci] repo-clustered bootstrap 95% CI: {summary['bootstrap_ci95_pct']}")
    print(f"[bootstrap_ci] {repos_with_recoverable}/{n_repos} repos ({summary['repos_with_recoverable_case_pct']}%) "
          f"contain >=1 recoverable case, Wilson 95% CI: {summary['repos_with_recoverable_case_wilson_ci95_pct']}")
    print(f"[bootstrap_ci] wrote {args.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
