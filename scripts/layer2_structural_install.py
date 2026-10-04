#!/usr/bin/env python3
"""
scripts/layer2_structural_install.py

Layer 2 of docs/phase2_protocol.md: real `npm ci --ignore-scripts` (actual
node_modules on disk, actual tarball downloads, ZERO code execution --
--ignore-scripts is npm's hard execution boundary, not a convenience flag)
for a bounded, pre-committed sample of Layer-1-CONFIRMED (outcome=="OK")
candidates only. Also collects the first real B0/B1/PDR Gate D data point:
`npm audit signatures` status, compared between the unmodified tree (B0/B1
reference, one install per repo) and each candidate's substituted tree.

Sample is fixed in docs/phase2_protocol.md Section 4, not re-selected here.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pdr.sandbox import PackageJsonCache, load_jsonl, append_jsonl  # noqa: E402
from scripts.layer1_resolution import patch_package_json_for_candidate  # noqa: E402

RESOLVE_DIR = "results/raw/resolve_phase1"
PKG_CACHE_DIR = "results/raw/provenance_phase1/package_jsons"
LAYER1_RESULTS = "results/processed/phase2_layer1_results.jsonl"
OUT_PATH = "results/processed/phase2_layer2_results.jsonl"

# Frozen sample, docs/phase2_protocol.md Section 4 -- up to 5 confirmed
# candidates per repo; some repos in the original protocol list turned out
# to have zero Layer-1-OK candidates (noted, not silently substituted).
SAMPLE_CAPS = {
    "axios/axios": 5,
    "mozilla/source-map": 5,
    "koajs/koa": 2,
    "tj/commander.js": 1,
    # nodeca/js-yaml, eemeli/yaml: 0 Layer-1-OK candidates available -- see
    # docs/phase2_layer2_results.md for the accounting.
}


def run_npm_ci(cwd: str, timeout: int = 180) -> dict:
    t0 = time.time()
    try:
        proc = subprocess.run(
            ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"],
            cwd=cwd, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"install_ok": False, "outcome": "TIMEOUT", "wall_time_s": round(time.time() - t0, 2)}
    wall = round(time.time() - t0, 2)
    if proc.returncode != 0:
        return {"install_ok": False, "outcome": "INSTALL_FAIL",
                "npm_stderr_tail": proc.stderr[-500:], "wall_time_s": wall}
    node_modules_exists = os.path.isdir(os.path.join(cwd, "node_modules"))
    return {"install_ok": True, "outcome": "OK", "wall_time_s": wall,
            "node_modules_created": node_modules_exists}


def run_audit_signatures(cwd: str, timeout: int = 60) -> dict:
    try:
        proc = subprocess.run(
            ["npm", "audit", "signatures"],
            cwd=cwd, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ran": False, "detail": "timeout"}
    # `npm audit signatures` exits nonzero when it finds anything to flag --
    # that's a normal, informative result here, not a script failure.
    return {"ran": True, "exit_code": proc.returncode,
            "stdout_tail": proc.stdout[-1500:], "stderr_tail": proc.stderr[-500:]}


def install_and_audit(pkg: dict, lock: dict, label: str, needs_reresolve: bool) -> dict:
    """`npm ci` refuses to run unless package.json and package-lock.json are
    already mutually consistent (verified empirically: it errors out rather
    than silently accepting a package.json whose dependency field doesn't
    match what the lockfile already resolved -- this is npm ci's actual
    contract, not a bug). For the PDR-substituted tree, the incoming (pkg,
    lock) pair is NOT yet consistent -- `pkg` has the candidate patched in,
    `lock` is still the original resolution. So: first regenerate a
    consistent lockfile with the same `npm install --package-lock-only
    --ignore-scripts` step Layer 1 already validated (needs_reresolve=True),
    THEN run the real `npm ci --ignore-scripts` against that now-consistent
    pair. The B0/B1 baseline tree's (pkg, lock) pair is already consistent
    by construction (it's the repo's real, as-fetched files), so it skips
    straight to `npm ci` (needs_reresolve=False).
    """
    with tempfile.TemporaryDirectory(prefix=f"pdr_layer2_{label}_") as tmp:
        with open(os.path.join(tmp, "package.json"), "w", encoding="utf-8") as f:
            json.dump(pkg, f)
        with open(os.path.join(tmp, "package-lock.json"), "w", encoding="utf-8") as f:
            json.dump(lock, f)

        if needs_reresolve:
            reresolve = subprocess.run(
                ["npm", "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund"],
                cwd=tmp, capture_output=True, text=True, timeout=60,
            )
            if reresolve.returncode != 0:
                return {"install": {"install_ok": False, "outcome": "RESOLUTION_FAIL",
                                     "npm_stderr_tail": reresolve.stderr[-500:]}}

        install = run_npm_ci(tmp)
        result = {"install": install}
        if install["install_ok"]:
            result["audit_signatures"] = run_audit_signatures(tmp)
        return result


def select_candidates(layer1_rows: list, caps: dict) -> tuple:
    """Pure selection logic (extracted for tests/test_layer2_selection.py):
    given Layer 1 results and a per-repo cap, return (selected, per_repo_count).
    Only outcome=="OK" rows from repos in `caps` are eligible; first-seen
    order is preserved (deterministic given a fixed input order) up to each
    repo's cap."""
    confirmed = [r for r in layer1_rows if r.get("outcome") == "OK" and r.get("repo") in caps]
    selected = []
    per_repo_count = {repo: 0 for repo in caps}
    for r in confirmed:
        repo = r["repo"]
        if per_repo_count[repo] < caps[repo]:
            selected.append(r)
            per_repo_count[repo] += 1
    return selected, per_repo_count


def main() -> int:
    layer1 = load_jsonl(LAYER1_RESULTS)
    selected, per_repo_count = select_candidates(layer1, SAMPLE_CAPS)

    print(f"[layer2] selected {len(selected)} candidates: {per_repo_count}")
    for repo, cap in SAMPLE_CAPS.items():
        if per_repo_count[repo] == 0:
            print(f"[layer2]   NOTE: {repo} had 0 Layer-1-OK candidates available (target was {cap})")

    already_done = {r["edge_id"] for r in load_jsonl(OUT_PATH)}
    pkg_cache = PackageJsonCache(PKG_CACHE_DIR)

    # One B0/B1 baseline install per repo (not per candidate) -- the
    # unmodified tree doesn't depend on which candidate is being tested.
    baseline_cache: dict = {}

    for c in selected:
        if c["edge_id"] in already_done:
            continue
        repo = c["repo"]
        safe_repo = repo.replace("/", "_")
        lock_path = os.path.join(RESOLVE_DIR, f"{safe_repo}.lock.json")
        with open(lock_path, "r", encoding="utf-8") as f:
            orig_lock = json.load(f)
        pkg = pkg_cache.get(repo)
        if pkg is None:
            append_jsonl(OUT_PATH, {"edge_id": c["edge_id"], "repo": repo, "error": "no package.json"})
            continue

        if repo not in baseline_cache:
            print(f"[layer2] {repo}: running B0/B1 baseline install...")
            baseline_cache[repo] = install_and_audit(pkg, orig_lock, "baseline", needs_reresolve=False)
            print(f"[layer2]   baseline install_ok={baseline_cache[repo]['install']['install_ok']} "
                  f"({baseline_cache[repo]['install'].get('wall_time_s')}s)")

        patched_pkg = patch_package_json_for_candidate(pkg, c["dep_name"], c["candidate_version"])
        print(f"[layer2] {repo}: {c['dep_name']} -> {c['candidate_version']} (PDR substitution)...")
        pdr_result = install_and_audit(patched_pkg, orig_lock, "pdr", needs_reresolve=True)
        print(f"[layer2]   PDR install_ok={pdr_result['install']['install_ok']} "
              f"({pdr_result['install'].get('wall_time_s')}s)")

        record = {
            "edge_id": c["edge_id"], "repo": repo, "dep_name": c["dep_name"],
            "resolved_version": c["resolved_version"], "candidate_version": c["candidate_version"],
            "b0_b1_baseline": baseline_cache[repo],
            "pdr": pdr_result,
        }
        append_jsonl(OUT_PATH, record)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
