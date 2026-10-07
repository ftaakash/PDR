#!/usr/bin/env python3
"""
scripts/scale_layer1.py [--workers W]

Layer 1 for the scale_v1 corpus (docs/phase4_protocol.md Section 3): every
DEFICIENT_RESOLUTION_PRESERVING edge in results/raw/provenance_scale/edges.csv,
same procedure as scripts/layer1_resolution.py (patch_package_json_for_candidate,
`npm install --package-lock-only --ignore-scripts`, OK iff the candidate is
applied and no other top-level version changes). Each (repo, package,
candidate) is resolved once; results are written per edge, append-only and
resumable, to results/processed/scale_v1_layer1.jsonl. Set PDR_NPM_CLI to
npm 10.9.7's npm-cli.js to match the tool lock.
"""
from __future__ import annotations

import argparse
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
from pdr.layer1_alt import classify_npm_failure  # noqa: E402
from pdr.sandbox import (OK, RIPPLE, TIMEOUT, PackageJsonCache, append_jsonl, load_jsonl,  # noqa: E402
                         patch_package_json_for_candidate, top_level_versions)

EDGES = "results/raw/provenance_scale/edges.csv"
RESOLVE_DIR = "results/raw/resolve_scale"
PKG_DIR = "results/raw/provenance_scale/package_jsons"
OUT = "results/processed/scale_v1_layer1.jsonl"
NPM_CLI = os.environ.get("PDR_NPM_CLI")


def npm(args):
    return (["node", NPM_CLI, *args], False) if NPM_CLI else (["npm", *args], os.name == "nt")


def resolve(repo: str, dep: str, version: str, pkg_cache: PackageJsonCache) -> dict:
    with open(os.path.join(RESOLVE_DIR, repo.replace("/", "_") + ".lock.json"), encoding="utf-8") as f:
        lock = json.load(f)
    pkg = pkg_cache.get(repo)
    if pkg is None:
        return {"outcome": "RESOLUTION_FAIL", "detail": "no package.json"}
    pkg = patch_package_json_for_candidate(pkg, dep, version)
    before = top_level_versions(lock)
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="pdr_scale_l1_", ignore_cleanup_errors=True) as tmp:
        json.dump(pkg, open(os.path.join(tmp, "package.json"), "w", encoding="utf-8"))
        json.dump(lock, open(os.path.join(tmp, "package-lock.json"), "w", encoding="utf-8"))
        cmd, shell = npm(["install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund"])
        try:
            p = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True, timeout=120, shell=shell,
                               encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            return {"outcome": TIMEOUT, "wall_time_s": round(time.time() - t0, 2)}
        if p.returncode != 0:
            return {"outcome": classify_npm_failure(p.stderr), "npm_stderr_head": p.stderr[:300],
                    "wall_time_s": round(time.time() - t0, 2)}
        new = json.load(open(os.path.join(tmp, "package-lock.json"), encoding="utf-8"))
    after = top_level_versions(new)
    ripple = {n: {"before": before.get(n), "after": v} for n, v in after.items()
              if n != dep and before.get(n) != v}
    applied = after.get(dep) == version
    return {"outcome": OK if (applied and not ripple) else RIPPLE, "candidate_actually_applied": applied,
            "n_ripple": len(ripple), "ripple_sample": dict(list(ripple.items())[:5]),
            "wall_time_s": round(time.time() - t0, 2)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    edges = []
    with open(EDGES, encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f)):
            if row["state"] == "DEFICIENT_RESOLUTION_PRESERVING":
                edges.append({"edge_id": f"{row['repo']}#{i}", "repo": row["repo"], "dep_name": row["dep_name"],
                              "resolved_version": row["resolved_version"],
                              "candidate_version": row["candidate_version"]})
    done = {r["edge_id"] for r in load_jsonl(OUT)}
    todo = [e for e in edges if e["edge_id"] not in done]
    groups: dict = {}
    for e in todo:
        groups.setdefault((e["repo"], e["dep_name"], e["candidate_version"]), []).append(e)
    print(f"[scale_l1] {len(edges)} candidate edges, {len(done)} done, {len(groups)} substitutions to resolve "
          f"(npm {'10.9.7 via PDR_NPM_CLI' if NPM_CLI else 'on PATH'})", flush=True)
    pkg_cache = PackageJsonCache(PKG_DIR)
    lock, n = threading.Lock(), [0]

    def work(item):
        (repo, dep, ver), es = item
        r = resolve(repo, dep, ver, pkg_cache)
        with lock:
            for e in es:
                append_jsonl(OUT, {**e, **r})
            n[0] += 1
            if n[0] % 100 == 0:
                print(f"[scale_l1] {n[0]}/{len(groups)}", flush=True)

    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        list(pool.map(work, sorted(groups.items())))
    print(f"[scale_l1] done: {len(load_jsonl(OUT))} edge results", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
