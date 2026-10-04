#!/usr/bin/env python3
"""
scripts/layer1_resolution.py [--limit N]

Layer 1 of docs/phase2_protocol.md: for every DEFICIENT_RESOLUTION_PRESERVING
candidate in the Phase 1 corpus, force the candidate via a real `overrides`
entry against the repo's actual package.json + package-lock.json, and
re-resolve with `npm install --package-lock-only --ignore-scripts`. Safe --
no node_modules, no tarball download, no code execution (see
docs/phase2_protocol.md Section 2).

Resumable: results are appended to a JSONL file as they complete, and
already-completed edge_ids are skipped on the next invocation -- this is the
same pattern check_provenance.py uses for packument caching, needed here
because Layer 1 covers ~2,349 candidates and a single invocation may not
finish inside one tool call's time budget.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pdr.sandbox import (  # noqa: E402
    PackageJsonCache, top_level_versions, load_jsonl, append_jsonl,
    RESOLUTION_FAIL, RIPPLE, OK, TIMEOUT,
    DEP_KIND_FIELDS, patch_package_json_for_candidate,  # re-exported: tests + layer2 import from here
)

EDGES_CSV = "results/raw/provenance_phase1/edges.csv"
RESOLVE_DIR = "results/raw/resolve_phase1"
PKG_CACHE_DIR = "results/raw/provenance_phase1/package_jsons"
OUT_PATH = "results/processed/phase2_layer1_results.jsonl"

def run_one(repo: str, dep_name: str, resolved_version: str, candidate_version: str,
            edge_id: str, parent_path: str, dep_kind: str, pkg_cache: PackageJsonCache) -> dict:
    safe_repo = repo.replace("/", "_")
    lock_path = os.path.join(RESOLVE_DIR, f"{safe_repo}.lock.json")
    with open(lock_path, "r", encoding="utf-8") as f:
        orig_lock = json.load(f)

    pkg = pkg_cache.get(repo)
    if pkg is None:
        return {"edge_id": edge_id, "repo": repo, "dep_name": dep_name,
                "resolved_version": resolved_version, "candidate_version": candidate_version,
                "outcome": RESOLUTION_FAIL, "detail": "could not fetch package.json"}

    pkg = patch_package_json_for_candidate(pkg, dep_name, candidate_version)

    before = top_level_versions(orig_lock)
    t0 = time.time()

    with tempfile.TemporaryDirectory(prefix="pdr_layer1_") as tmp:
        with open(os.path.join(tmp, "package.json"), "w", encoding="utf-8") as f:
            json.dump(pkg, f)
        with open(os.path.join(tmp, "package-lock.json"), "w", encoding="utf-8") as f:
            json.dump(orig_lock, f)
        try:
            proc = subprocess.run(
                ["npm", "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund"],
                cwd=tmp, capture_output=True, text=True, timeout=60,
            )
        except subprocess.TimeoutExpired:
            return {"edge_id": edge_id, "repo": repo, "dep_name": dep_name,
                    "resolved_version": resolved_version, "candidate_version": candidate_version,
                    "outcome": TIMEOUT, "wall_time_s": round(time.time() - t0, 2)}

        wall_time = round(time.time() - t0, 2)
        if proc.returncode != 0:
            return {"edge_id": edge_id, "repo": repo, "dep_name": dep_name,
                    "resolved_version": resolved_version, "candidate_version": candidate_version,
                    "outcome": RESOLUTION_FAIL, "npm_stderr_tail": proc.stderr[-500:],
                    "wall_time_s": wall_time}

        with open(os.path.join(tmp, "package-lock.json"), "r", encoding="utf-8") as f:
            new_lock = json.load(f)
        after = top_level_versions(new_lock)
        actual_resolved = after.get(dep_name)
        ripple = {name: {"before": before.get(name), "after": v}
                  for name, v in after.items()
                  if name != dep_name and before.get(name) != v}

        outcome = OK if (actual_resolved == candidate_version and not ripple) else RIPPLE
        return {
            "edge_id": edge_id, "repo": repo, "dep_name": dep_name,
            "resolved_version": resolved_version, "candidate_version": candidate_version,
            "outcome": outcome,
            "candidate_actually_applied": actual_resolved == candidate_version,
            "n_ripple": len(ripple),
            "ripple_sample": dict(list(ripple.items())[:5]),
            "wall_time_s": wall_time,
        }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                     help="max NEW candidates to process this invocation (for resumability across tool calls)")
    args = ap.parse_args()

    already_done = {r["edge_id"] for r in load_jsonl(OUT_PATH)}
    print(f"[layer1] {len(already_done)} candidates already completed (resuming)")

    candidates = []
    with open(EDGES_CSV, "r", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f)):
            if row["state"] != "DEFICIENT_RESOLUTION_PRESERVING":
                continue
            edge_id = f"{row['repo']}#{i}"
            if edge_id in already_done:
                continue
            candidates.append({
                "edge_id": edge_id, "repo": row["repo"], "dep_name": row["dep_name"],
                "resolved_version": row["resolved_version"], "candidate_version": row["candidate_version"],
                "parent_path": row["parent_path"], "dep_kind": row["dep_kind"],
            })

    print(f"[layer1] {len(candidates)} candidates remaining")
    if args.limit:
        candidates = candidates[:args.limit]
        print(f"[layer1] processing {len(candidates)} this invocation (--limit {args.limit})")

    pkg_cache = PackageJsonCache(PKG_CACHE_DIR)
    t_start = time.time()
    for n, c in enumerate(candidates, 1):
        r = run_one(c["repo"], c["dep_name"], c["resolved_version"], c["candidate_version"],
                    c["edge_id"], c["parent_path"], c["dep_kind"], pkg_cache)
        append_jsonl(OUT_PATH, r)
        if n % 50 == 0 or n == len(candidates):
            elapsed = time.time() - t_start
            print(f"[layer1] {n}/{len(candidates)} this run, {elapsed:.0f}s elapsed")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
