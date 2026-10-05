#!/usr/bin/env python3
"""
scripts/layer1_report.py

Summary of Phase 2 Layer 1 (results/processed/phase2_layer1_results.jsonl)
-> results/processed/layer1_summary.json:

  * outcome counts;
  * resolution-confirmed (OK) rate, edge-weighted and repo-weighted, each with
    a repository-clustered bootstrap CI (pdr.stats.clustered);
  * per-repo table;
  * concentration: share of candidates in the top-3 repos, repos at 0% and
    >=50% OK, distinct (repo, package, candidate) substitutions behind OK edges;
  * ripple-size SENSITIVITY analysis (TASKS.md T2; thresholds k in
    {0, 1, 2, 5, 10} declared there before computing). This does not replace
    the frozen k = 0 definition; see pdr.stats.ok_within_ripple.
"""
from __future__ import annotations

import collections
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pdr.sandbox import load_jsonl  # noqa: E402
from pdr.stats import clustered, ok_within_ripple  # noqa: E402

LAYER1 = "results/processed/phase2_layer1_results.jsonl"
OUT = "results/processed/layer1_summary.json"
RIPPLE_KS = (0, 1, 2, 5, 10)


def by_repo(rows, pred):
    out = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        out[r["repo"]][1] += 1
        out[r["repo"]][0] += bool(pred(r))
    return dict(out)


def build(rows: list) -> dict:
    cnt = collections.Counter(r["outcome"] for r in rows)
    ok = by_repo(rows, lambda r: r["outcome"] == "OK")
    n_by_repo = collections.Counter(r["repo"] for r in rows)
    top3 = n_by_repo.most_common(3)
    rates = {repo: v[0] / v[1] for repo, v in ok.items()}
    per_repo = sorted(({"repo": repo, "n": v[1], "ok": v[0], "ok_pct": round(100 * v[0] / v[1], 1),
                        **{k: c for k, c in collections.Counter(r["outcome"] for r in rows
                                                                 if r["repo"] == repo).items()}}
                       for repo, v in ok.items()), key=lambda x: (-x["n"], x["repo"]))
    sens = {}
    for k in RIPPLE_KS:
        sens[str(k)] = clustered(by_repo(rows, lambda r, k=k: ok_within_ripple(r, k)))
    return {
        "n": len(rows), "outcomes": dict(cnt),
        "ok_rate": clustered(ok),
        "concentration": {
            "top3_repos": [r for r, _ in top3],
            "top3_share_pct": round(100 * sum(n for _, n in top3) / len(rows), 1),
            "repos_with_candidates": len(ok),
            "repos_zero_ok": sum(1 for v in rates.values() if v == 0),
            "repos_ge50_ok": sum(1 for v in rates.values() if v >= 0.5),
            "distinct_ok_substitutions": len({(r["repo"], r["dep_name"], r["candidate_version"])
                                              for r in rows if r["outcome"] == "OK"}),
        },
        "ripple_sensitivity": {"label": "sensitivity analysis; k=0 is the frozen definition",
                               "ks": list(RIPPLE_KS), "by_k": sens},
        "per_repo": per_repo,
    }


def main() -> int:
    out = build(load_jsonl(LAYER1))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    o = out["ok_rate"]
    print(f"[layer1_report] OK {o['edge_weighted_pct']}% {o['edge_weighted_ci95_pct']} edge-weighted; "
          f"{o['repo_weighted_pct']}% {o['repo_weighted_ci95_pct']} repo-weighted")
    for k, s in out["ripple_sensitivity"]["by_k"].items():
        print(f"  k<={k:>2}: {s['edge_weighted_pct']:6.2f}% {s['edge_weighted_ci95_pct']} | "
              f"repo {s['repo_weighted_pct']}% {s['repo_weighted_ci95_pct']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
