#!/usr/bin/env python3
"""
scripts/scale_select_experiments.py

Layer 3 cohort for scale_v1 (docs/phase4_protocol.md Section 4), outcome-blind:
inputs are only Layer 1 results, the pinned config and each repository's
package.json at its pinned SHA. Unique (repo, package, candidate) with Layer 1
OK, hermetic text screen identical to the micro-pilot's, per-repository cap 5
chosen with a seeded shuffle. Writes the hash-locked manifest and a pins file
in the orchestrator's format (every repository is already commit-pinned).
"""
from __future__ import annotations

import datetime
import json
import os
import random
import sys

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from phase3_select_micropilot import (NON_HERMETIC_KEYWORDS, NON_HERMETIC_REPOS,  # noqa: E402
                                      canonical_sha256, patch_mode, screen_repo)
from pdr.sandbox import load_jsonl  # noqa: E402

SEED = 20261007
PER_REPO_CAP = 5
CONFIG = "configs/experiments/scale_v1.yaml"
LAYER1 = "results/processed/scale_v1_layer1.jsonl"
PKG_DIR = "results/raw/provenance_scale/package_jsons"
OUT = "configs/experiments/scale_v1_manifest.json"
HASH_OUT = "configs/experiments/scale_v1_manifest.sha256"
PINS_OUT = "configs/experiments/scale_v1_pins.json"


def select(experiments_by_repo: dict, cap: int, seed: int) -> list:
    """Pure: per repository, sort by experiment_id, seeded shuffle, keep `cap`."""
    out = []
    for repo in sorted(experiments_by_repo):
        es = sorted(experiments_by_repo[repo], key=lambda e: e["experiment_id"])
        random.Random(f"{seed}:{repo}").shuffle(es)
        out.extend(es[:cap])
    return sorted(out, key=lambda e: e["experiment_id"])


def main() -> int:
    cfg = yaml.safe_load(open(CONFIG, encoding="utf-8"))
    meta = {r["repo"]: r for r in cfg["repos"]}
    ok = [r for r in load_jsonl(LAYER1) if r["outcome"] == "OK"]
    pkgs, screens, excluded = {}, {}, {}
    for repo in sorted({r["repo"] for r in ok}):
        p = os.path.join(PKG_DIR, repo.replace("/", "_") + ".package.json")
        pkgs[repo] = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None
        cmd, reason = screen_repo(repo, pkgs[repo])
        if cmd:
            screens[repo] = cmd
        else:
            excluded[repo] = reason
    exps: dict = {}
    for r in ok:
        if r["repo"] not in screens:
            continue
        key = (r["repo"], r["dep_name"], r["candidate_version"])
        e = exps.setdefault(key, {"repo": r["repo"], "dep_name": r["dep_name"],
                                  "resolved_version": r["resolved_version"],
                                  "candidate_version": r["candidate_version"], "edge_ids": [],
                                  "size_bucket": meta[r["repo"]]["strata"]["band"],
                                  "test_command": screens[r["repo"]]})
        e["edge_ids"].append(r["edge_id"])
    by_repo: dict = {}
    for e in exps.values():
        e["edge_ids"].sort()
        e["patch_mode"], e["dep_field"] = patch_mode(pkgs[e["repo"]], e["dep_name"])
        e["experiment_id"] = f"{e['repo']}::{e['dep_name']}@{e['candidate_version']}"
        by_repo.setdefault(e["repo"], []).append(e)
    selected = select(by_repo, PER_REPO_CAP, SEED)
    manifest = {
        "protocol": "docs/phase4_protocol.md", "experiment": "scale_v1",
        "generated_on": datetime.date.today().isoformat(), "outcome_blind": True,
        "frozen_parameters": {"seed": SEED, "per_repo_cap": PER_REPO_CAP,
                              "non_hermetic_keywords": NON_HERMETIC_KEYWORDS,
                              "non_hermetic_repos": NON_HERMETIC_REPOS},
        "pool": {"layer1_ok_edges": len(ok), "unique_experiments_after_screen": len(exps),
                 "repos_with_ok": len({r["repo"] for r in ok}), "repos_excluded_by_screen": excluded},
        "n_selected": len(selected), "selected": selected,
    }
    json.dump(manifest, open(OUT, "w", encoding="utf-8"), indent=2, sort_keys=True)
    open(HASH_OUT, "w").write(canonical_sha256(manifest) + "\n")
    pins = {repo: {"repo": repo, "status": "PINNED", "sha": m["ref"], "source": "scale_v1 selection"}
            for repo, m in meta.items()}
    json.dump(pins, open(PINS_OUT, "w", encoding="utf-8"), indent=2, sort_keys=True)
    print(f"[scale_select] OK edges {len(ok)}; experiments after screen {len(exps)} in {len(by_repo)} repos; "
          f"excluded repos {len(excluded)}; selected {len(selected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
