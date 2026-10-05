#!/usr/bin/env python3
"""
scripts/layer1_alt_report.py [--allow-incomplete]

Pre-specified analysis for experiment layer1_alt_v1 (docs/phase2_protocol.md
Section 7). Reads the Layer 1 results, the frozen retry plan and the attempt
log, and writes results/processed/layer1_alt_v1_summary.json:

  * primary: exists-any resolution-confirmed rate over all proxy-positive
    edges, edge-weighted and repo-weighted, each with a repository-clustered
    percentile bootstrap CI (5,000 resamples, seed 20260928), next to the
    single-candidate (Layer 1) rate computed the same way;
  * secondary: alternative-OK rate within the RIPPLE/PEER_CONFLICT population,
    NO_ALTERNATIVE share, first-OK attempt index and attempts-used
    distributions, outcome counts per attempt index, attempt-0 concordance;
  * per-repo table.

Refuses to write a summary while any planned attempt is missing unless
--allow-incomplete is given (then the summary is marked incomplete).
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pdr.layer1_alt import summarise_edge  # noqa: E402
from pdr.sandbox import OK, load_jsonl  # noqa: E402
from pdr.stats import clustered  # noqa: E402,F401  (re-exported for tests)

LAYER1 = "results/processed/phase2_layer1_results.jsonl"
PLAN = "results/processed/layer1_alt_v1_plan.json"
ATTEMPTS = "results/processed/layer1_alt_v1_attempts.jsonl"
OUT = "results/processed/layer1_alt_v1_summary.json"


def build(layer1: list, plan: dict, attempts: list) -> dict:
    outcomes = {(a["repo"], a["dep_name"], a["version"]): a["outcome"] for a in attempts}
    l1 = {r["edge_id"]: r for r in layer1}
    edges, missing = [], 0
    for e in plan["edges"]:
        key0 = (e["repo"], e["dep_name"], e["original_candidate"])
        per_pkg = {v: outcomes[(e["repo"], e["dep_name"], v)] for v in e["alternatives"]
                   if (e["repo"], e["dep_name"], v) in outcomes}
        try:
            s = summarise_edge(e["alternatives"], per_pkg, outcomes[key0])
        except KeyError:
            missing += 1
            continue
        edges.append({**e, **s, "attempt0_outcome": outcomes[key0]})

    single = collections.defaultdict(lambda: [0, 0])
    anyv = collections.defaultdict(lambda: [0, 0])
    done_ids = {e["edge_id"] for e in edges}
    pop_ids = {e["edge_id"] for e in plan["edges"]}
    credited = {e["edge_id"] for e in edges if e["credited"]}
    # Best case for edges this host could not run: every blocked edge with >=1
    # alternative would have recovered. Reported as a bound, never as the estimate.
    blocked_best = {e["edge_id"] for e in edges if e["status"] == "PLATFORM_BLOCKED" and e["alternatives"]}
    upper = collections.defaultdict(lambda: [0, 0])
    for r in layer1:
        if r["edge_id"] in pop_ids and r["edge_id"] not in done_ids:
            continue  # incomplete edge: excluded from both rates so they stay comparable
        single[r["repo"]][1] += 1
        anyv[r["repo"]][1] += 1
        single[r["repo"]][0] += r["outcome"] == OK
        anyv[r["repo"]][0] += r["outcome"] == OK or r["edge_id"] in credited
        upper[r["repo"]][1] += 1
        upper[r["repo"]][0] += r["outcome"] == OK or r["edge_id"] in credited or r["edge_id"] in blocked_best

    pop = [e for e in edges]
    alt_pop = collections.defaultdict(lambda: [0, 0])
    for e in pop:
        alt_pop[e["repo"]][1] += 1
        alt_pop[e["repo"]][0] += e["credited"]

    per_attempt = collections.defaultdict(collections.Counter)
    for e in pop:
        for i, o in enumerate(e["alt_outcomes"], 1):
            per_attempt[i][o] += 1
    conc = collections.Counter((e["layer1_outcome"], e["attempt0_outcome"]) for e in pop)
    subs = {(e["repo"], e["dep_name"]): (e["layer1_outcome"], e["attempt0_outcome"]) for e in pop}

    per_repo = []
    for repo in sorted(single):
        n = single[repo][1]
        per_repo.append({"repo": repo, "n": n, "single_ok": single[repo][0], "exists_any_ok": anyv[repo][0],
                         "single_ok_pct": round(100 * single[repo][0] / n, 1),
                         "exists_any_ok_pct": round(100 * anyv[repo][0] / n, 1)})

    return {
        "experiment_id": plan["experiment_id"], "k_max": plan["k_max"], "t_cut": plan["t_cut"],
        "complete": missing == 0, "population_edges": len(plan["edges"]),
        "population_edges_summarised": len(pop), "population_edges_missing_attempts": missing,
        "n_attempts": len(attempts),
        "primary": {"single_candidate": clustered(single), "exists_any": clustered(anyv)},
        "platform_blocked": {
            "edges": sum(e["status"] == "PLATFORM_BLOCKED" for e in pop),
            "edges_with_alternatives": len(blocked_best),
            "repos": sorted({e["repo"] for e in pop if e["status"] == "PLATFORM_BLOCKED"}),
            "exists_any_upper_bound": clustered(upper),
        },
        "secondary": {
            "alt_ok_within_population": clustered(alt_pop) if alt_pop else None,
            "status_counts": dict(collections.Counter(e["status"] for e in pop)),
            "no_alternative": sum(e["alt_status"] == "NO_ALTERNATIVE" for e in pop),
            "first_ok_index_dist": dict(sorted(collections.Counter(
                e["first_ok_index"] for e in pop if e["alt_status"] == "ALT_OK").items())),
            "attempts_used_when_exhausted_dist": dict(sorted(collections.Counter(
                e["attempts_used"] for e in pop if e["alt_status"] == "ALT_EXHAUSTED").items())),
            "outcomes_by_attempt_index": {str(i): dict(c) for i, c in sorted(per_attempt.items())},
            "attempt0_concordance_edges": {f"{a}->{b}": n for (a, b), n in sorted(conc.items())},
            "attempt0_concordance_substitutions": {f"{a}->{b}": n for (a, b), n in sorted(
                collections.Counter(subs.values()).items())},
            "drift_ok_edges": sum(e["drift"] for e in pop),
        },
        "per_repo": per_repo,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-incomplete", action="store_true")
    a = ap.parse_args()
    out = build(load_jsonl(LAYER1), json.load(open(PLAN, encoding="utf-8")), load_jsonl(ATTEMPTS))
    if not out["complete"] and not a.allow_incomplete:
        print(f"[report] incomplete: {out['population_edges_missing_attempts']} edges lack attempts; "
              f"re-run scripts/layer1_alt_resolution.py run (or pass --allow-incomplete)")
        return 1
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    p = out["primary"]
    print(f"[report] single-candidate {p['single_candidate']['edge_weighted_pct']}% "
          f"{p['single_candidate']['edge_weighted_ci95_pct']} | exists-any {p['exists_any']['edge_weighted_pct']}% "
          f"{p['exists_any']['edge_weighted_ci95_pct']}; repo-weighted {p['single_candidate']['repo_weighted_pct']}% "
          f"-> {p['exists_any']['repo_weighted_pct']}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
