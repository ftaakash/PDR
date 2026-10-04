#!/usr/bin/env python3
"""
scripts/fetch_corpus.py --config configs/experiments/kill_v1.yaml

Downloads the real `package-lock.json` committed in each repo named in the
config (GitHub "owner/repo" + optional ref + optional path), parses it with
pdr.resolve, and writes:
    results/raw/resolve/<repo_safe>.lock.json        (raw lockfile, for audit trail)
    results/raw/resolve/<repo_safe>.edges.jsonl       (parsed Edge objects, one per line)
    results/raw/resolve/_manifest.json                (what was actually fetched, for reproducibility)

No repository is cloned -- we only fetch the single committed lockfile via
raw.githubusercontent.com, which is enough to reconstruct the resolved
dependency tree (see pdr/resolve.py for why a lockfile alone is sufficient).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pdr.resolve import load_and_parse  # noqa: E402

try:
    import yaml
except ImportError:
    yaml = None

USER_AGENT = "pdr-research-pilot/0.1"


def _load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if yaml is not None:
        return yaml.safe_load(text)
    # Minimal fallback: config files in this project are also valid JSON.
    return json.loads(text)


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--out-dir", default="results/raw/resolve")
    args = ap.parse_args()

    cfg = _load_config(args.config)
    repos = cfg["repos"]
    os.makedirs(args.out_dir, exist_ok=True)

    manifest = {"config": args.config, "repos": []}

    for r in repos:
        repo = r["repo"]
        ref = r.get("ref", "HEAD")
        lock_path = r.get("lockfile_path", "package-lock.json")
        safe = repo.replace("/", "_")

        url = f"https://raw.githubusercontent.com/{repo}/{ref}/{lock_path}"
        print(f"[fetch_corpus] {repo} <- {url}")
        try:
            raw = _fetch(url)
        except urllib.error.HTTPError as e:
            print(f"[fetch_corpus]   FAILED ({e.code}) -- skipping {repo}")
            manifest["repos"].append({"repo": repo, "ok": False, "error": f"HTTP {e.code}"})
            continue

        lock_out = os.path.join(args.out_dir, f"{safe}.lock.json")
        with open(lock_out, "wb") as f:
            f.write(raw)

        try:
            edges = load_and_parse(repo, lock_out)
        except ValueError as e:
            print(f"[fetch_corpus]   PARSE FAILED -- {e}")
            manifest["repos"].append({"repo": repo, "ok": False, "error": str(e)})
            continue

        edges_out = os.path.join(args.out_dir, f"{safe}.edges.jsonl")
        with open(edges_out, "w", encoding="utf-8") as f:
            for e in edges:
                f.write(json.dumps(dataclasses.asdict(e)) + "\n")

        print(f"[fetch_corpus]   OK -- {len(edges)} edges")
        manifest["repos"].append({
            "repo": repo, "ok": True, "ref": ref, "n_edges": len(edges),
            "lockfile_bytes": len(raw),
        })

    with open(os.path.join(args.out_dir, "_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    n_ok = sum(1 for x in manifest["repos"] if x["ok"])
    print(f"[fetch_corpus] done: {n_ok}/{len(repos)} repos fetched")
    return 0 if n_ok > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
