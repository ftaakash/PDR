#!/usr/bin/env python3
"""
scripts/check_claims.py [--show]

Recomputes every headline number the docs rely on DIRECTLY from the raw data
files and compares it to docs/claims.json. Exit status 1 on any mismatch.

Why this exists: this project's numbers are quoted in many documents
(README, PILOT_RUN_REPORT, docs/*.md). During development, several quoted
figures were wrong or stale (e.g. a pin count transcribed incorrectly, an
edge-weighted rate quoted without its interval). The registry makes that kind
of drift a failing test instead of a reviewer's discovery.

Rules for changing docs/claims.json: a value may only change in the SAME
commit as (a) the data change that justifies it and (b) the doc edits that
quote it. Never edit claims.json merely to make this check pass.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import random
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
from pdr.stats import clustered as clustered_full, ok_within_ripple  # noqa: E402
DEFICIENT = {"DEFICIENT_UNRECOVERABLE", "DEFICIENT_SEMANTIC_ONLY", "DEFICIENT_RESOLUTION_PRESERVING"}
RECOVERABLE = {"DEFICIENT_SEMANTIC_ONLY", "DEFICIENT_RESOLUTION_PRESERVING"}
TOL = 0.011  # percentages are recorded to 2 decimals


def p(*parts):
    return os.path.join(ROOT, *parts)


def edge_stats(path):
    c, repos, n = collections.Counter(), set(), 0
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            c[row["state"]] += 1
            repos.add(row["repo"])
            n += 1
    known = n - c["UNKNOWN"]
    defi = sum(c[s] for s in DEFICIENT)
    rec = sum(c[s] for s in RECOVERABLE)
    return {
        "edges": n, "repos": len(repos), "unknown_pct": round(100 * c["UNKNOWN"] / n, 2),
        "opg_pct": round(100 * defi / known, 2), "semantic_recovery_pct": round(100 * rec / defi, 2),
        "deficient_edges": defi, "proxy_positive_edges": c["DEFICIENT_RESOLUTION_PRESERVING"],
    }


def jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def clustered_ci(rows, seed=20260928, n_boot=5000):
    by = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        by[r["repo"]][1] += 1
        by[r["repo"]][0] += r["outcome"] == "OK"
    repos = sorted(by)
    rng = random.Random(seed)
    boots = []
    for _ in range(n_boot):
        s = [by[repos[rng.randrange(len(repos))]] for _ in repos]
        boots.append(sum(x[0] for x in s) / sum(x[1] for x in s))
    boots.sort()
    macro = [v[0] / v[1] for v in by.values()]
    return round(100 * boots[int(.025 * (n_boot - 1))], 1), round(100 * boots[int(.975 * (n_boot - 1))], 1), \
        round(100 * sum(macro) / len(macro), 1)


def compute():
    out = {}
    out["pilot7"] = edge_stats(p("results", "raw", "provenance", "edges.csv"))
    out["phase1_45"] = edge_stats(p("results", "raw", "provenance_phase1", "edges.csv"))
    boot = json.load(open(p("results", "processed", "phase1_bootstrap.json")))
    out["phase1_bootstrap"] = {"point_pct": boot["point_estimate_pct"], "ci95_pct": boot["bootstrap_ci95_pct"],
                               "repos_with_recoverable": boot["repos_with_recoverable_case"]}
    l1 = jsonl(p("results", "processed", "phase2_layer1_results.jsonl"))
    cnt = collections.Counter(r["outcome"] for r in l1)
    lo, hi, macro = clustered_ci(l1)
    out["layer1"] = {"n": len(l1), "unique_edge_ids": len({r["edge_id"] for r in l1}), "OK": cnt["OK"],
                     "RIPPLE": cnt["RIPPLE"], "PEER_CONFLICT": cnt["PEER_CONFLICT"],
                     "RESOLUTION_FAIL": cnt["RESOLUTION_FAIL"],
                     "ok_pct_pooled": round(100 * cnt["OK"] / len(l1), 2),
                     "ok_pct_ci95_clustered": [lo, hi], "ok_pct_repo_macro_mean": macro}
    def by_repo(pred):
        d = collections.defaultdict(lambda: [0, 0])
        for r in l1:
            d[r["repo"]][1] += 1
            d[r["repo"]][0] += bool(pred(r))
        return d
    full = clustered_full(by_repo(lambda r: r["outcome"] == "OK"))
    out["layer1_summary"] = {
        "ok_pct_repo_weighted_ci95": full["repo_weighted_ci95_pct"],
        "ok_pct_repo_weighted_median": full["repo_weighted_median_pct"],
        "ripple_sensitivity": {str(k): {kk: c[kk] for kk in ("successes", "edge_weighted_pct",
                                                              "edge_weighted_ci95_pct", "repo_weighted_pct",
                                                              "repo_weighted_ci95_pct")}
                               for k in (0, 1, 2, 5, 10)
                               for c in [clustered_full(by_repo(lambda r, k=k: ok_within_ripple(r, k)))]},
    }
    import importlib.util
    spec = importlib.util.spec_from_file_location("l1alt", p("scripts", "layer1_alt_report.py"))
    l1alt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(l1alt)
    alt = l1alt.build(l1, json.load(open(p("results", "processed", "layer1_alt_v1_plan.json"), encoding="utf-8")),
                      jsonl(p("results", "processed", "layer1_alt_v1_attempts.jsonl")))
    pick = ("successes", "edge_weighted_pct", "edge_weighted_ci95_pct", "repo_weighted_pct", "repo_weighted_ci95_pct")
    sec = alt["secondary"]
    out["layer1_alt_v1"] = {
        "complete": alt["complete"], "population_edges": alt["population_edges"], "n_attempts": alt["n_attempts"],
        "exists_any": {k: alt["primary"]["exists_any"][k] for k in pick},
        "alt_ok_within_population": {k: sec["alt_ok_within_population"][k] for k in pick},
        "status_counts": sec["status_counts"],
        "first_ok_index_dist": {str(k): v for k, v in sec["first_ok_index_dist"].items()},
        "attempt0_concordance_substitutions": sec["attempt0_concordance_substitutions"],
        "platform_blocked_edges": alt["platform_blocked"]["edges"],
        "platform_blocked_edges_with_alternatives": alt["platform_blocked"]["edges_with_alternatives"],
        "exists_any_upper_bound": {k: alt["platform_blocked"]["exists_any_upper_bound"][k] for k in pick},
    }
    spec3 = importlib.util.spec_from_file_location("p3r", p("scripts", "phase3_report.py"))
    p3r = importlib.util.module_from_spec(spec3)
    spec3.loader.exec_module(p3r)
    m = p3r.build(jsonl(p("results", "processed", "phase3_micropilot_results.jsonl")))
    out["phase3_micropilot"] = {
        "n_records": m["n_records"], "n_valid": m["n_valid"], "outcome_counts": m["outcome_counts"],
        "b0_invalid": m["flags"]["b0_invalid"], "REWORK": m["flags"]["REWORK"],
        "test_delta_n_pairs": m["primary"]["n_pairs"], "test_delta_new_failures": m["primary"]["new_failures_b"],
    }
    l2 = jsonl(p("results", "processed", "phase2_layer2_results.jsonl"))
    out["layer2"] = {"n": len(l2), "pdr_install_ok": sum(1 for r in l2 if r["pdr"]["install"]["install_ok"])}
    man = json.load(open(p("configs", "experiments", "phase3_micropilot_manifest.json")))
    pins = json.load(open(p("configs", "experiments", "phase3_micropilot_pins.json")))
    out["phase3_manifest"] = {
        "layer1_ok_edges": man["pool"]["layer1_ok_edges"],
        "unique_experiments_after_screen": man["pool"]["unique_experiments_after_screen"],
        "repos_excluded_by_screen": len(man["pool"]["repos_excluded_by_screen"]),
        "n_selected": man["n_selected"],
        "pinned": sum(1 for v in pins.values() if v["status"] == "PINNED"),
        "pinned_not_at_head": sorted(r for r, v in pins.items() if v["status"] == "PINNED" and not v.get("is_head")),
    }
    return out


def diff(expected, actual, path=""):
    bad = []
    if isinstance(expected, dict):
        for k, v in expected.items():
            if k.startswith("_"):
                continue
            if k not in actual:
                bad.append(f"{path}{k}: missing in recomputed data")
            else:
                bad += diff(v, actual[k], f"{path}{k}.")
    elif isinstance(expected, list):
        if len(expected) != len(actual):
            bad.append(f"{path[:-1]}: expected {expected}, got {actual}")
        else:
            for i, (e, a) in enumerate(zip(expected, actual)):
                bad += diff(e, a, f"{path}[{i}].")
    elif isinstance(expected, float) or isinstance(actual, float):
        if abs(float(expected) - float(actual)) > TOL:
            bad.append(f"{path[:-1]}: expected {expected}, got {actual}")
    elif expected != actual:
        bad.append(f"{path[:-1]}: expected {expected!r}, got {actual!r}")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true", help="print recomputed values and exit 0")
    args = ap.parse_args()
    actual = compute()
    if args.show:
        print(json.dumps(actual, indent=2))
        return 0
    expected = json.load(open(p("docs", "claims.json")))
    bad = diff(expected, actual)
    if bad:
        print("CLAIMS MISMATCH (docs/claims.json vs data):")
        for b in bad:
            print("  -", b)
        return 1
    print("claims OK: all registered numbers match the data files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
