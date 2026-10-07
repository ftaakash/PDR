#!/usr/bin/env python3
"""
scripts/scale_report.py [--allow-partial]

Pre-specified scale_v1 analysis (docs/phase4_protocol.md Section 6) ->
results/processed/scale_v1_summary.json. Pure analysis of files already on disk:
  results/raw/provenance_scale/edges.csv                 Phase 1 classification
  results/processed/scale_v1_layer1.jsonl                 Layer 1
  results/processed/scale_v1_screen.jsonl                 Stage A (merged shards)
  results/processed/scale_v1_layer3.jsonl                 Stage B (merged shards)
Every rate is edge/experiment-weighted and repo-weighted with a
repository-clustered bootstrap CI (pdr.stats.clustered); repository-level
proportions use a Wilson CI. Subgroups by star band and age are EXPLORATORY.
"""
from __future__ import annotations

import collections
import csv
import importlib.util
import json
import math
import os
import sys

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pdr import phase3 as p3  # noqa: E402
from pdr.sandbox import OK, load_jsonl  # noqa: E402
from pdr.stats import clustered  # noqa: E402

EDGES = "results/raw/provenance_scale/edges.csv"
CONFIG = "configs/experiments/scale_v1.yaml"
L1 = "results/processed/scale_v1_layer1.jsonl"
SCREEN = "results/processed/scale_v1_screen.jsonl"
L3 = "results/processed/scale_v1_layer3.jsonl"
OUT = "results/processed/scale_v1_summary.json"
DEFICIENT = {"DEFICIENT_UNRECOVERABLE", "DEFICIENT_SEMANTIC_ONLY", "DEFICIENT_RESOLUTION_PRESERVING"}
MIN_JUDGEABLE_FOR_RATE = 30


def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(100 * max(0, c - h), 1), round(100 * min(1, c + h), 1)]


def by_repo(rows, pred, repo_key="repo"):
    d = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        d[r[repo_key]][1] += 1
        d[r[repo_key]][0] += bool(pred(r))
    return dict(d)


def phase1(rows):
    known = [r for r in rows if r["state"] != "UNKNOWN"]
    deficient = [r for r in rows if r["state"] in DEFICIENT]
    return {
        "edges": len(rows), "repos": len({r["repo"] for r in rows}),
        "unknown_pct": round(100 * (len(rows) - len(known)) / len(rows), 2) if rows else None,
        "opg": clustered(by_repo(known, lambda r: r["state"] in DEFICIENT)),
        "proxy_positive_among_deficient": clustered(by_repo(
            deficient, lambda r: r["state"] == "DEFICIENT_RESOLUTION_PRESERVING")),
    }


def layer1(rows):
    runnable = [r for r in rows if r["outcome"] != "PLATFORM_BLOCKED"]
    return {"n": len(rows), "outcomes": dict(collections.Counter(r["outcome"] for r in rows)),
            "platform_blocked": len(rows) - len(runnable),
            "ok_rate": clustered(by_repo(runnable, lambda r: r["outcome"] == OK))}


def layer3(screen, records, meta):
    usable = [s for s in screen if s["usable"]]
    reasons = collections.Counter()
    for s in screen:
        if s["usable"]:
            continue
        b0 = s["b0"]
        if not p3.arm_has_result(b0):
            reasons["worker_error"] += 1
        elif p3.stage_kind(b0, "install") is not None:
            reasons["install_fail"] += 1
        else:
            reasons[f"tests_{s['b0_test_status'].lower()}"] += 1
    spec = importlib.util.spec_from_file_location("p3r", os.path.join(os.path.dirname(__file__), "phase3_report.py"))
    p3r = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p3r)
    rep = p3r.build(records) if records else None
    pairs = [(r, p3.classify_pair(r["b0"], r["pdr"])) for r in records if not p3.validate_record(r)]
    judge = [(r, c) for r, c in pairs if c["attributable"]["test"]]
    rate = None
    if len(judge) >= MIN_JUDGEABLE_FOR_RATE:
        rate = clustered(by_repo([dict(r, ok=c["outcome"] == OK) for r, c in judge], lambda x: x["ok"]))
    sub = {}
    for dim in ("band", "age"):
        g = collections.defaultdict(lambda: [0, 0])
        for r, c in judge:
            k = meta[r["repo"]]["strata"][dim]
            g[k][1] += 1
            g[k][0] += c["outcome"] == OK
        sub[dim] = {k: {"ok": v[0], "n": v[1]} for k, v in sorted(g.items())}
    return {
        "screened_repos": len(screen), "testable_repos": len(usable),
        "testable_pct": round(100 * len(usable) / len(screen), 1) if screen else None,
        "testable_wilson_ci95": wilson(len(usable), len(screen)),
        "untestable_reasons": dict(reasons),
        "experiments_run": len(records),
        "judgeable_experiments": len(judge), "judgeable_repos": len({r["repo"] for r, _ in judge}),
        "judgeable_outcomes": dict(collections.Counter(c["outcome"] for _, c in judge)),
        "ok_rate_among_judgeable": rate,
        "rate_reported": rate is not None,
        "report": rep,
        "exploratory_subgroups": sub,
    }


def main() -> int:
    meta = {r["repo"]: r for r in yaml.safe_load(open(CONFIG, encoding="utf-8"))["repos"]}
    with open(EDGES, encoding="utf-8") as f:
        edges = list(csv.DictReader(f))
    out = {"experiment": "scale_v1", "phase1": phase1(edges), "layer1": layer1(load_jsonl(L1))}
    out["layer3"] = layer3(load_jsonl(SCREEN), load_jsonl(L3), meta) if os.path.exists(SCREEN) else None
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1, default=str)
    print(json.dumps({k: v for k, v in out.items() if k != "layer3"}, indent=1, default=str)[:3000])
    if out["layer3"]:
        l3 = {k: v for k, v in out["layer3"].items() if k != "report"}
        print(json.dumps(l3, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
