#!/usr/bin/env python3
"""
scripts/layer1_alt_resolution.py plan
scripts/layer1_alt_resolution.py run [--limit N] [--workers W] [--budget-s S]

Experiment layer1_alt_v1 (docs/phase2_protocol.md Section 7).

`plan`  builds, deterministically and before any attempt, the per-edge retry
        list for every Layer 1 RIPPLE/PEER_CONFLICT edge and writes
        results/processed/layer1_alt_v1_plan.json.
`run`   executes attempts (attempt 0 = original candidate re-run, then each
        edge's alternatives in order, stopping at the edge's first OK). Each
        (repo, package, version) is run at most once; results are appended to
        results/processed/layer1_alt_v1_attempts.jsonl and skipped on resume.

Host-safe exactly as Layer 1: `npm install --package-lock-only
--ignore-scripts` in a temp dir, no node_modules, no lifecycle scripts.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pdr.layer1_alt import (EXPERIMENT_ID, K_MAX, T_CUT, alternative_candidates,  # noqa: E402
                            classify_npm_failure)
from pdr.provenance import fetch_packument  # noqa: E402
from pdr.sandbox import (OK, RIPPLE, TIMEOUT, PackageJsonCache, append_jsonl, load_jsonl,  # noqa: E402
                         patch_package_json_for_candidate, top_level_versions)
from pdr.semver_client import run_batch  # noqa: E402

EDGES_CSV = "results/raw/provenance_phase1/edges.csv"
LAYER1 = "results/processed/phase2_layer1_results.jsonl"
RESOLVE_DIR = "results/raw/resolve_phase1"
PKG_CACHE_DIR = "results/raw/provenance_phase1/package_jsons"
PACKUMENT_DIR = "results/raw/provenance_phase1/packuments"
PLAN = "results/processed/layer1_alt_v1_plan.json"
ATTEMPTS = "results/processed/layer1_alt_v1_attempts.jsonl"


def population():
    rows = {}
    with open(EDGES_CSV, encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f)):
            if row["state"] == "DEFICIENT_RESOLUTION_PRESERVING":
                rows[f"{row['repo']}#{i}"] = row
    pop = []
    for r in load_jsonl(LAYER1):
        if r["outcome"] == OK:
            continue
        row = rows[r["edge_id"]]
        assert row["dep_name"] == r["dep_name"] and row["candidate_version"] == r["candidate_version"], r["edge_id"]
        pop.append({"edge_id": r["edge_id"], "repo": r["repo"], "dep_name": r["dep_name"],
                    "declared_range": row["declared_range"], "resolved_version": r["resolved_version"],
                    "original_candidate": r["candidate_version"], "layer1_outcome": r["outcome"]})
    return pop


def cmd_plan() -> int:
    pop = population()
    names = sorted({e["dep_name"] for e in pop})
    print(f"[plan] {len(pop)} edges, {len(names)} packages; fetching packuments (cached)")
    pks = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for n, pk in zip(names, pool.map(lambda n: fetch_packument(n, PACKUMENT_DIR), names)):
            pks[n] = pk
    missing = [n for n in names if not pks[n].found]
    if missing:
        print(f"[plan] packuments not found: {missing}")
        return 1

    order = dict(zip(names, (r["result"] for r in run_batch(
        [{"op": "rsort", "versions": list(pks[n].versions)} for n in names]))))

    # Ask npm-semver only about provenance-bearing versions (the only ones that can qualify).
    tasks, idx = [], []
    for e in pop:
        for v, vf in pks[e["dep_name"]].versions.items():
            if not vf.has_provenance:
                continue
            for op in ({"op": "satisfies", "version": v, "range": e["declared_range"]},
                       {"op": "diff", "a": e["resolved_version"], "b": v},
                       {"op": "gt", "a": e["original_candidate"], "b": v}):
                tasks.append(op)
                idx.append((e["edge_id"], v, op["op"]))
    print(f"[plan] {len(tasks)} semver questions")
    facts = collections.defaultdict(dict)
    for (eid, v, op), res in zip(idx, run_batch(tasks)):
        if not res.get("ok"):
            raise RuntimeError(f"semver {op} failed for {eid} {v}: {res}")
        facts[eid].setdefault(v, {})[op] = res["result"]

    plan = {"experiment_id": EXPERIMENT_ID, "k_max": K_MAX, "t_cut": T_CUT, "edges": []}
    for e in pop:
        pk = pks[e["dep_name"]]
        vf = {}
        for v, f in facts[e["edge_id"]].items():
            vf[v] = {"has_provenance": True, "time": pk.versions[v].time, "satisfies": f["satisfies"],
                     "diff": f["diff"], "lt_original": f["gt"]}
        sel = alternative_candidates(order[e["dep_name"]], vf)
        plan["edges"].append({**e, **sel})
    with open(PLAN, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=1, sort_keys=True)
    dist = collections.Counter(len(e["alternatives"]) for e in plan["edges"])
    print(f"[plan] alternatives per edge: {dict(sorted(dist.items()))}")
    print(f"[plan] versions excluded by t_cut: {sum(e['n_excluded_by_t_cut'] for e in plan['edges'])}")
    return 0


def attempt(repo: str, dep_name: str, version: str, pkg_cache: PackageJsonCache, role: str) -> dict:
    """Same procedure as scripts/layer1_resolution.run_one (docs/phase2_protocol.md S7)."""
    base = {"experiment_id": EXPERIMENT_ID, "repo": repo, "dep_name": dep_name, "version": version, "role": role}
    with open(os.path.join(RESOLVE_DIR, repo.replace("/", "_") + ".lock.json"), encoding="utf-8") as f:
        orig_lock = json.load(f)
    pkg = patch_package_json_for_candidate(pkg_cache.get(repo), dep_name, version)
    before = top_level_versions(orig_lock)
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="pdr_l1alt_") as tmp:
        with open(os.path.join(tmp, "package.json"), "w", encoding="utf-8") as f:
            json.dump(pkg, f)
        with open(os.path.join(tmp, "package-lock.json"), "w", encoding="utf-8") as f:
            json.dump(orig_lock, f)
        try:
            proc = subprocess.run(
                ["npm", "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund"],
                cwd=tmp, capture_output=True, text=True, timeout=60, shell=(os.name == "nt"),
                encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            return {**base, "outcome": TIMEOUT, "wall_time_s": round(time.time() - t0, 2)}
        wall = round(time.time() - t0, 2)
        if proc.returncode != 0:
            return {**base, "outcome": classify_npm_failure(proc.stderr), "npm_stderr_head": proc.stderr[:400],
                    "npm_stderr_tail": proc.stderr[-400:], "wall_time_s": wall}
        with open(os.path.join(tmp, "package-lock.json"), encoding="utf-8") as f:
            new_lock = json.load(f)
    after = top_level_versions(new_lock)
    ripple = {n: {"before": before.get(n), "after": v} for n, v in after.items()
              if n != dep_name and before.get(n) != v}
    applied = after.get(dep_name) == version
    return {**base, "outcome": OK if (applied and not ripple) else RIPPLE, "candidate_actually_applied": applied,
            "n_ripple": len(ripple), "ripple_sample": dict(list(ripple.items())[:5]), "wall_time_s": wall}


def cmd_run(limit, workers, budget_s) -> int:
    plan = json.load(open(PLAN, encoding="utf-8"))
    done = {(r["repo"], r["dep_name"], r["version"]): r["outcome"] for r in load_jsonl(ATTEMPTS)}
    print(f"[run] {len(done)} attempts already recorded")
    groups = collections.defaultdict(list)
    for e in plan["edges"]:
        groups[(e["repo"], e["dep_name"])].append(e)
    pkg_cache = PackageJsonCache(PKG_CACHE_DIR)
    lock, counter, t0 = threading.Lock(), [0], time.time()

    def get(repo, dep, v, role):
        key = (repo, dep, v)
        with lock:
            if key in done:
                return done[key]
            if (limit and counter[0] >= limit) or time.time() - t0 > budget_s:
                return None
            counter[0] += 1
        r = attempt(repo, dep, v, pkg_cache, role)
        with lock:
            append_jsonl(ATTEMPTS, r)
            done[key] = r["outcome"]
        return r["outcome"]

    def work(item):
        (repo, dep), edges = item
        if get(repo, dep, edges[0]["original_candidate"], "attempt0") is None:
            return False
        for e in edges:
            for v in e["alternatives"]:
                o = get(repo, dep, v, "alternative")
                if o is None:
                    return False
                if o == OK:
                    break
        return True

    with ThreadPoolExecutor(max_workers=workers) as pool:
        finished = list(pool.map(work, sorted(groups.items())))
    print(f"[run] {counter[0]} new attempts in {time.time() - t0:.0f}s; "
          f"{sum(finished)}/{len(finished)} (repo, package) groups complete")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["plan", "run"])
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--budget-s", type=int, default=10 ** 9)
    a = ap.parse_args()
    return cmd_plan() if a.cmd == "plan" else cmd_run(a.limit, a.workers, a.budget_s)


if __name__ == "__main__":
    raise SystemExit(main())
