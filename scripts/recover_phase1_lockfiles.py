#!/usr/bin/env python3
"""
scripts/recover_phase1_lockfiles.py [--only owner/repo,...] [--budget-s N]

The Phase 1 lockfiles (results/raw/resolve_phase1/<repo>.lock.json) are inputs
to Layer 1 and to layer1_alt_v1, but they were not carried over in the
handoff: only _manifest.json survived. They were fetched from each repo's
HEAD without a commit SHA, so this script recovers them from git history and
accepts a candidate ONLY if it is provably the analyzed file:

  1. If configs/experiments/phase3_micropilot_pins.json records the analyzed
     lockfile's git blob ID for the repo, the blob must match exactly
     (byte-identical by construction).
  2. Otherwise the candidate must (a) have exactly the byte length recorded in
     _manifest.json and (b) re-parse (pdr.resolve) to exactly the same edge
     multiset that results/raw/provenance_phase1/edges.csv holds for that repo
     (parent_path, dep_name, declared_range, dep_kind, resolved_version).

Candidates are the commits touching package-lock.json at or before the
handoff import date, newest first. Git metadata/blob reads only (treeless
clone + lazy blob fetch); nothing from the repository is executed.

Repos with no accepted candidate are recorded UNRECOVERED with the reason and
are never silently substituted with HEAD.

Output: the lockfile at results/raw/resolve_phase1/<repo>.lock.json (git-ignored,
regenerable) and the evidence record results/processed/phase1_lockfile_recovery.json.
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
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pdr.resolve import parse_lockfile  # noqa: E402

MANIFEST = "results/raw/resolve_phase1/_manifest.json"
LOCK_DIR = "results/raw/resolve_phase1"
EDGES_CSV = "results/raw/provenance_phase1/edges.csv"
PINS = "configs/experiments/phase3_micropilot_pins.json"
OUT = "results/processed/phase1_lockfile_recovery.json"
UNTIL = "2026-10-04T23:59:59Z"   # handoff import date; Phase 1 necessarily predates it
WINDOW = 60                       # lockfile-touching commits examined per repo


def edge_key(parent_path, dep_name, declared_range, dep_kind, resolved_version):
    return (parent_path, dep_name, declared_range, dep_kind, resolved_version or "")


def expected_edges() -> dict:
    out = collections.defaultdict(collections.Counter)
    with open(EDGES_CSV, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[row["repo"]][edge_key(row["parent_path"], row["dep_name"], row["declared_range"],
                                      row["dep_kind"], row["resolved_version"])] += 1
    return out


def git(*args, cwd=None, timeout=300, text=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=text, timeout=timeout)
    if r.returncode != 0:
        err = r.stderr if text else r.stderr.decode("utf-8", "replace")
        raise RuntimeError(f"git {' '.join(args[:3])} failed: {err.strip()[:200]}")
    return r.stdout


def recover(repo: str, want_bytes: int, want_blob: str | None, want_edges: collections.Counter) -> tuple:
    with tempfile.TemporaryDirectory(prefix="pdr_recover_") as tmp:
        git("clone", "--quiet", "--bare", "--filter=blob:none", f"https://github.com/{repo}.git", tmp, timeout=400)
        shas = git("log", f"-n{WINDOW}", f"--until={UNTIL}", "--format=%H %cI", "--", "package-lock.json",
                   cwd=tmp).split("\n")
        seen_blobs, examined = set(), 0
        for line in shas:
            if not line.strip():
                continue
            sha, cdate = line.split()
            try:
                blob = git("rev-parse", f"{sha}:package-lock.json", cwd=tmp).strip()
            except RuntimeError:
                continue  # lockfile deleted in this commit
            if blob in seen_blobs:
                continue
            seen_blobs.add(blob)
            examined += 1
            if want_blob is not None:
                if blob != want_blob:
                    continue
                raw = git("cat-file", "blob", blob, cwd=tmp, text=False)
                return raw, {"repo": repo, "status": "RECOVERED", "sha": sha, "commit_date": cdate,
                             "blob": blob, "evidence": "git blob id == phase3 pins lock_blob",
                             "bytes": len(raw), "blobs_examined": examined}
            raw = git("cat-file", "blob", blob, cwd=tmp, text=False)
            if len(raw) != want_bytes:
                continue
            edges = parse_lockfile(repo, json.loads(raw.decode("utf-8")))
            got = collections.Counter(edge_key(e.parent_path, e.dep_name, e.declared_range, e.dep_kind,
                                               e.resolved_version) for e in edges)
            if got == want_edges:
                return raw, {"repo": repo, "status": "RECOVERED", "sha": sha, "commit_date": cdate,
                             "blob": blob, "evidence": "byte length == manifest AND edge multiset == edges.csv",
                             "bytes": len(raw), "n_edges": len(edges), "blobs_examined": examined}
        return None, {"repo": repo, "status": "UNRECOVERED", "blobs_examined": examined,
                      "reason": f"no lockfile blob in the newest {WINDOW} lockfile commits matched"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated repos")
    ap.add_argument("--budget-s", type=int, default=280)
    args = ap.parse_args()

    manifest = json.load(open(MANIFEST, encoding="utf-8"))
    pins = json.load(open(PINS, encoding="utf-8")) if os.path.exists(PINS) else {}
    record = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    want = expected_edges()
    repos = [r for r in manifest["repos"] if r.get("ok")]
    if args.only:
        repos = [r for r in repos if r["repo"] in args.only.split(",")]

    t0 = time.time()
    for r in repos:
        repo = r["repo"]
        if record.get(repo, {}).get("status") == "RECOVERED" and \
                os.path.exists(os.path.join(LOCK_DIR, repo.replace("/", "_") + ".lock.json")):
            continue
        if time.time() - t0 > args.budget_s:
            print(f"[recover] budget reached; re-run to continue")
            break
        print(f"[recover] {repo} ...", flush=True)
        want_blob = pins.get(repo, {}).get("lock_blob") if pins.get(repo, {}).get("status") == "PINNED" else None
        try:
            raw, rec = recover(repo, r["lockfile_bytes"], want_blob, want[repo])
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            raw, rec = None, {"repo": repo, "status": "UNRECOVERED", "reason": str(e)[:300]}
        if raw is not None:
            with open(os.path.join(LOCK_DIR, repo.replace("/", "_") + ".lock.json"), "wb") as f:
                f.write(raw)
        record[repo] = rec
        print(f"[recover]   {rec['status']} {rec.get('sha', '')[:10]} {rec.get('reason', '')}", flush=True)
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, sort_keys=True)

    n_ok = sum(1 for v in record.values() if v["status"] == "RECOVERED")
    print(f"[recover] {n_ok}/{len(manifest['repos'])} recovered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
