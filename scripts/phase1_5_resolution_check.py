#!/usr/bin/env python3
"""
scripts/phase1_5_resolution_check.py

Phase 1.5 (tiny C/D pilot, per docs/methodology_freeze.md Section 6): before
building the full Gate C/D harness, run a small, real experiment to see
whether pdr/policy.py's resolution-preserving PROXY (local semver diff
against the currently resolved version) agrees with what npm's ACTUAL
resolver does when the candidate is forced via `overrides`.

SAFETY / SCOPE (deliberate, not an oversight): this runs ONLY
    npm install --package-lock-only --ignore-scripts --no-audit --no-fund
against a temp copy of each repo's real package.json + package-lock.json.
This resolves the dependency graph against the live registry but does NOT
download tarballs, does NOT create node_modules, and does NOT execute any
package's lifecycle scripts. It is the "resolution-verification" stage --
lighter and safer than the "structural" (`npm ci --ignore-scripts`, real
install to disk) and "behavioral" (scripts enabled) modes the full Gate C/D
harness will need. Those two are explicitly DEFERRED to Phase 2, which
requires the per-experiment isolated-worker sandbox described in
docs/methodology_freeze.md Section 7 -- this shared session container is not
that sandbox, so nothing here executes untrusted code from the packages
being studied.

For each selected (repo, dep_name, resolved_version, candidate_version)
triple:
  1. Fetch the repo's real root package.json (not just the lockfile).
  2. Copy it + the already-fetched package-lock.json into an isolated temp dir.
  3. Add {"overrides": {dep_name: candidate_version}} (merged with any
     existing overrides).
  4. Run the resolution-only npm command above.
  5. Record: did it succeed; did dep_name actually resolve to
     candidate_version; which OTHER top-level resolved versions changed as a
     side effect (the dedup/hoisting ripple our local proxy cannot see).
  6. Compare outcome against the proxy's prediction (which was: this
     candidate is resolution-preserving).
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

USER_AGENT = "pdr-research-pilot/0.1"


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def top_level_versions(lock: dict) -> dict:
    out = {}
    for path, entry in lock.get("packages", {}).items():
        if path.startswith("node_modules/") and "/node_modules/" not in path[len("node_modules/"):]:
            name = path[len("node_modules/"):]
            if "version" in entry:
                out[name] = entry["version"]
    return out


def run_one(repo: str, dep_name: str, resolved_version: str, candidate_version: str,
            edge_id: str, resolve_dir: str) -> dict:
    safe_repo = repo.replace("/", "_")
    lock_src = os.path.join(resolve_dir, f"{safe_repo}.lock.json")
    with open(lock_src, "r", encoding="utf-8") as f:
        orig_lock = json.load(f)

    pkg_json_url = f"https://raw.githubusercontent.com/{repo}/HEAD/package.json"
    try:
        pkg_text = fetch_text(pkg_json_url)
        pkg = json.loads(pkg_text)
    except Exception as e:  # noqa: BLE001
        return {"repo": repo, "dep_name": dep_name, "edge_id": edge_id, "ok": False,
                "error": f"could not fetch package.json: {e}"}

    overrides = dict(pkg.get("overrides") or {})
    overrides[dep_name] = candidate_version
    pkg["overrides"] = overrides

    before = top_level_versions(orig_lock)

    with tempfile.TemporaryDirectory(prefix="pdr_phase15_") as tmp:
        with open(os.path.join(tmp, "package.json"), "w", encoding="utf-8") as f:
            json.dump(pkg, f)
        with open(os.path.join(tmp, "package-lock.json"), "w", encoding="utf-8") as f:
            json.dump(orig_lock, f)

        proc = subprocess.run(
            ["npm", "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund"],
            cwd=tmp, capture_output=True, text=True, timeout=90,
        )
        result = {
            "repo": repo, "edge_id": edge_id, "dep_name": dep_name,
            "resolved_version_before": resolved_version, "candidate_version": candidate_version,
            "npm_exit_code": proc.returncode,
            "npm_ok": proc.returncode == 0,
        }
        if proc.returncode != 0:
            result["npm_stderr_tail"] = proc.stderr[-800:]
            result["proxy_confirmed"] = False
            return result

        with open(os.path.join(tmp, "package-lock.json"), "r", encoding="utf-8") as f:
            new_lock = json.load(f)
        after = top_level_versions(new_lock)

        actual_resolved = after.get(dep_name)
        result["actual_resolved_after_override"] = actual_resolved
        result["candidate_actually_applied"] = (actual_resolved == candidate_version)

        # ripple: other top-level packages whose resolved version changed
        ripple = {name: {"before": before.get(name), "after": v}
                  for name, v in after.items()
                  if name != dep_name and before.get(name) != v}
        result["n_other_top_level_versions_changed"] = len(ripple)
        result["ripple_sample"] = dict(list(ripple.items())[:5])

        # our proxy already predicted "resolution-preserving" for every triple
        # fed into this script; "confirmed" means real resolution agreed:
        # override applied cleanly, no ripple elsewhere.
        result["proxy_confirmed"] = bool(result["candidate_actually_applied"] and len(ripple) == 0)
        return result


def main() -> int:
    resolve_dir = "results/raw/resolve_phase1"
    edges_csv = "results/raw/provenance_phase1/edges.csv"

    # Fixed, pre-committed selection (documented in docs/phase1_5_results.md):
    # 5 repos spanning lockfileVersion v2/v3, monorepo/non-monorepo, and
    # small/medium size buckets; up to 6 candidates per repo.
    selection_repos = {
        "axios/axios": 5,
        "koajs/koa": 2,
        "tj/commander.js": 2,
        "redis/node-redis": 6,
        "mozilla/source-map": 6,
    }

    candidates = []
    with open(edges_csv, "r", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f)):
            if row["state"] != "DEFICIENT_RESOLUTION_PRESERVING":
                continue
            repo = row["repo"]
            if repo not in selection_repos:
                continue
            if sum(1 for c in candidates if c["repo"] == repo) >= selection_repos[repo]:
                continue
            candidates.append({
                "edge_id": f"{repo}#{i}",
                "repo": repo,
                "dep_name": row["dep_name"],
                "resolved_version": row["resolved_version"],
                "candidate_version": row["candidate_version"],
            })

    print(f"[phase1_5] selected {len(candidates)} candidates across {len(selection_repos)} repos")

    results = []
    for c in candidates:
        print(f"[phase1_5] {c['repo']}: {c['dep_name']} {c['resolved_version']} -> {c['candidate_version']}")
        r = run_one(c["repo"], c["dep_name"], c["resolved_version"], c["candidate_version"],
                    c["edge_id"], resolve_dir)
        results.append(r)
        status = "OK" if r.get("npm_ok") else "NPM_FAILED"
        confirmed = r.get("proxy_confirmed")
        print(f"           -> {status}, proxy_confirmed={confirmed}")

    os.makedirs("results/processed", exist_ok=True)
    out_path = "results/processed/phase1_5_resolution_check.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    n = len(results)
    n_npm_ok = sum(1 for r in results if r.get("npm_ok"))
    n_confirmed = sum(1 for r in results if r.get("proxy_confirmed"))
    n_applied = sum(1 for r in results if r.get("candidate_actually_applied"))
    n_with_ripple = sum(1 for r in results if r.get("n_other_top_level_versions_changed", 0) > 0)
    print(f"\n[phase1_5] {n_npm_ok}/{n} npm resolutions succeeded")
    print(f"[phase1_5] {n_applied}/{n} candidates actually applied by npm's real resolver")
    print(f"[phase1_5] {n_with_ripple}/{n} triggered a ripple (other top-level versions changed)")
    print(f"[phase1_5] {n_confirmed}/{n} fully confirmed (applied cleanly, zero ripple) "
          f"-- proxy/actual-resolution agreement rate: "
          f"{round(100*n_confirmed/n, 1) if n else 'NA'}%")
    print(f"[phase1_5] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
