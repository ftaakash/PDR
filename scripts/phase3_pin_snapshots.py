#!/usr/bin/env python3
"""
scripts/phase3_pin_snapshots.py [--materialize]

The lockfiles analyzed in Phases 1-2 were fetched from each repo's HEAD
WITHOUT recording a commit SHA. Layer 3 needs the repo's real source (its
test suite!) at a commit consistent with those lockfiles. This script
recovers that commit rather than assuming HEAD hasn't moved.

Method (git only -- git clone/log/rev-parse/archive never execute repository
code; no npm, no scripts):
  1. Treeless clone (--filter=blob:none --no-checkout): full commit+tree
     history, no file contents downloaded.
  2. `git hash-object` on the STORED lockfile bytes gives its blob ID
     locally, with no network. Compare against `git rev-parse <sha>:package-lock.json`
     for candidate commits (tree lookups only -- no blob download).
  3. For lockfile-matching commits, also require the cached package.json
     (parsed-JSON equality) to match, since package.json was fetched
     separately from the lockfile. Newest commit satisfying both is the pin.
  4. If none is found within the search window, the repo is recorded as
     UNRESOLVED with the reason -- never silently pinned to HEAD.

Output: configs/experiments/phase3_micropilot_pins.json (resumable).
--materialize additionally exports the pinned tree (no .git) to
results/raw/phase3_snapshots/<repo>/ via `git archive`.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

MANIFEST = "configs/experiments/phase3_micropilot_manifest.json"
PINS = "configs/experiments/phase3_micropilot_pins.json"
LOCK_DIR = "results/raw/resolve_phase1"
PKG_DIR = "results/raw/provenance_phase1/package_jsons"
SNAP_DIR = "results/raw/phase3_snapshots"
WINDOW = 400   # max commits (touching either file) examined per repo


def git(*args, cwd=None, timeout=120, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:3])} failed: {r.stderr.strip()[:200]}")
    return r.stdout.strip()


def resolve_pin(repo: str) -> dict:
    safe = repo.replace("/", "_")
    lock_path = os.path.join(LOCK_DIR, f"{safe}.lock.json")
    pkg_path = os.path.join(PKG_DIR, f"{safe}.package.json")
    stored_pkg = json.load(open(pkg_path))
    with tempfile.TemporaryDirectory(prefix="pdr_pin_", ignore_cleanup_errors=True) as tmp:
        try:
            git("clone", "--quiet", "--filter=blob:none", "--no-checkout",
                f"https://github.com/{repo}.git", tmp, timeout=200)
        except Exception as e:  # noqa: BLE001
            return {"repo": repo, "status": "UNRESOLVED", "reason": f"clone failed: {e}"}
        want_blob = git("hash-object", lock_path)
        head = git("rev-parse", "HEAD", cwd=tmp)
        candidates = [head] + git("log", f"-n{WINDOW}", "--format=%H", "--", "package-lock.json", "package.json",
                                  cwd=tmp).split()
        seen, examined = set(), 0
        for sha in candidates:
            if sha in seen:
                continue
            seen.add(sha)
            examined += 1
            r = subprocess.run(["git", "rev-parse", f"{sha}:package-lock.json"], cwd=tmp, capture_output=True, text=True)
            if r.returncode != 0 or r.stdout.strip() != want_blob:
                continue
            try:
                pj = json.loads(git("show", f"{sha}:package.json", cwd=tmp))
            except Exception:  # noqa: BLE001
                continue
            if pj == stored_pkg:
                return {"repo": repo, "status": "PINNED", "sha": sha, "is_head": sha == head,
                        "head_at_pin_time": head, "commits_examined": examined,
                        "lock_blob": want_blob}
        return {"repo": repo, "status": "UNRESOLVED", "head_at_pin_time": head, "commits_examined": examined,
                "reason": "no commit in window has both the analyzed lockfile blob and the cached package.json"}


def materialize(repo: str, sha: str) -> str:
    dest = os.path.join(SNAP_DIR, repo.replace("/", "_"))
    if os.path.isdir(dest) and os.listdir(dest):
        return dest
    os.makedirs(dest, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pdr_snap_", ignore_cleanup_errors=True) as tmp:
        git("-c", "maintenance.auto=false", "-c", "gc.auto=0", "clone", "--quiet", "--filter=blob:none", "--no-checkout", f"https://github.com/{repo}.git", tmp, timeout=250)
        p1 = subprocess.Popen(["git", "archive", sha], cwd=tmp, stdout=subprocess.PIPE)
        subprocess.run(["tar", "-x", "-C", dest, "--no-same-owner", "--no-same-permissions"], stdin=p1.stdout, check=True)
        p1.wait()
    return dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--materialize", action="store_true")
    ap.add_argument("--only", help="comma-separated repos (default: all in manifest)")
    ap.add_argument("--budget-s", type=int, default=240, help="stop starting new repos after this many seconds")
    args = ap.parse_args()

    import time
    t0 = time.time()
    manifest = json.load(open(MANIFEST))
    repos = sorted({e["repo"] for e in manifest["selected"]})
    if args.only:
        repos = [r for r in repos if r in args.only.split(",")]
    pins = json.load(open(PINS)) if os.path.exists(PINS) else {}

    for repo in repos:
        if repo in pins and pins[repo]["status"] == "PINNED":
            continue
        if time.time() - t0 > args.budget_s:
            print(f"[pin] budget reached; re-run to continue ({repo} onward pending)")
            break
        print(f"[pin] {repo} ...", flush=True)
        try:
            pins[repo] = resolve_pin(repo)
        except subprocess.TimeoutExpired:
            pins[repo] = {"repo": repo, "status": "UNRESOLVED", "reason": "git timeout"}
        print(f"[pin]   {pins[repo]['status']}"
              + (f" sha={pins[repo]['sha'][:10]} head={pins[repo]['is_head']}" if pins[repo]['status'] == 'PINNED' else f" ({pins[repo].get('reason')})"),
              flush=True)
        json.dump(pins, open(PINS, "w"), indent=2, sort_keys=True)

    if args.materialize:
        for repo in repos:
            if pins.get(repo, {}).get("status") == "PINNED":
                print(f"[pin] materialize {repo} -> {materialize(repo, pins[repo]['sha'])}")

    done = sum(1 for r in repos if r in pins and pins[r]["status"] == "PINNED")
    print(f"[pin] {done}/{len(repos)} repos pinned; "
          f"{sum(1 for r in repos if r in pins and pins[r]['status']=='UNRESOLVED')} unresolved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
