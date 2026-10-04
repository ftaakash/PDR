#!/usr/bin/env python3
"""
scripts/phase3_select_micropilot.py

Selects the Phase 3 behavioral micro-pilot cohort from Layer-1-CONFIRMED
(outcome == "OK") candidates and writes a hash-locked manifest.

OUTCOME-BLIND BY CONSTRUCTION: no Layer 3 result exists when this runs, and
nothing here reads one. Inputs are only (a) Layer 1 results, (b) Phase 1's
per-repo size strata, (c) each repo's fetched package.json. Every parameter
that could steer the sample (seed, allocation, per-repo cap, exclusion rules)
is a constant below, frozen before any behavioral run and recorded in the
manifest. `isolated_worker/orchestrate.py` refuses to run unless the
manifest's SHA-256 matches the committed MANIFEST.sha256, so the cohort
cannot be quietly edited after outcomes start arriving.

Experiment unit: (repo, dep_name, candidate_version). Several edges in one
repo can imply the identical substitution (the PDR arm's package.json patch
depends only on this triple), so they are ONE experiment; the manifest keeps
all their edge_ids so results still map back to edges.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import random
import sys
from collections import defaultdict

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pdr.sandbox import DEP_KIND_FIELDS, load_jsonl  # noqa: E402

# ---- FROZEN PARAMETERS (docs/phase3_protocol.md Section 6) -------------------
SEED = 20260928
ALLOCATION = {"small": 5, "medium": 10, "large": 10}   # very_large excluded from micro-pilot (compute)
PER_REPO_CAP = 3
# Direct-dependency floor (added in design revision v2, BEFORE any behavioral run: the v1 draft
# happened to select 1 direct-field experiment of 23 because only ~5% of the pool is direct-field;
# the reviewer asked for both modes, so the floor is now a frozen parameter). Applies to the
# buckets that contain any direct-field experiments.
DIRECT_FLOOR = {"medium": 1, "large": 3}
DEFAULT_TEST = 'echo "Error: no test specified" && exit 1'
# Static "hermetic-test screen": test scripts that (by their text alone) need a
# browser, a git submodule, or an external service cannot be judged fairly by a
# generic worker image. Excluded for the micro-pilot; later phases may extend
# the image and re-admit them. Applied to script TEXT only -- never to outcomes.
NON_HERMETIC_KEYWORDS = ["browser", "chrome", "playwright", "puppeteer", "wireit",
                         "submodule", "e2e", "selenium", "docker"]
NON_HERMETIC_REPOS = {"redis/node-redis": "tests require a running Redis server"}

LAYER1 = "results/processed/phase2_layer1_results.jsonl"
CONFIG = "configs/experiments/kill_v1_phase1_n45.yaml"
PKG_DIR = "results/raw/provenance_phase1/package_jsons"
OUT = "configs/experiments/phase3_micropilot_manifest.json"
HASH_OUT = "configs/experiments/phase3_micropilot_manifest.sha256"


def canonical_sha256(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def screen_repo(repo: str, pkg: dict | None):
    """Return (test_command, None) if usable, else (None, reason)."""
    if repo in NON_HERMETIC_REPOS:
        return None, NON_HERMETIC_REPOS[repo]
    if pkg is None:
        return None, "no package.json"
    script = ((pkg.get("scripts") or {}).get("test") or "").strip()
    if not script or script == DEFAULT_TEST:
        return None, "no real test script"
    low = script.lower()
    for kw in NON_HERMETIC_KEYWORDS:
        if kw in low:
            return None, f"test script mentions '{kw}' (non-hermetic screen)"
    return "npm test", None


def patch_mode(pkg: dict, dep_name: str):
    for f in sorted(DEP_KIND_FIELDS):
        if dep_name in (pkg.get(f) or {}):
            return "direct_field", f
    return "overrides", None


def round_robin_pick(by_repo: dict, quota: int, rng: random.Random, taken=None):
    repos = sorted(by_repo)
    rng.shuffle(repos)
    for r in repos:
        rng.shuffle(by_repo[r])
    picked = []
    taken = taken if taken is not None else defaultdict(int)
    progressed = True
    while len(picked) < quota and progressed:
        progressed = False
        for r in repos:
            if len(picked) >= quota:
                break
            if taken[r] < PER_REPO_CAP and by_repo[r]:
                picked.append(by_repo[r].pop())
                taken[r] += 1
                progressed = True
    return picked


def main() -> int:
    cfg = yaml.safe_load(open(CONFIG))
    strata = {r["repo"]: r["strata"] for r in cfg["repos"]}
    ok = [r for r in load_jsonl(LAYER1) if r["outcome"] == "OK"]

    pkgs, screens, excluded = {}, {}, {}
    for repo in sorted({r["repo"] for r in ok}):
        p = os.path.join(PKG_DIR, repo.replace("/", "_") + ".package.json")
        pkgs[repo] = json.load(open(p)) if os.path.exists(p) else None
        cmd, reason = screen_repo(repo, pkgs[repo])
        if cmd:
            screens[repo] = cmd
        else:
            excluded[repo] = reason

    # experiments = unique (repo, dep_name, candidate_version); keep every edge_id
    experiments = {}
    for r in ok:
        if r["repo"] not in screens:
            continue
        key = (r["repo"], r["dep_name"], r["candidate_version"])
        e = experiments.setdefault(key, {
            "repo": r["repo"], "dep_name": r["dep_name"], "resolved_version": r["resolved_version"],
            "candidate_version": r["candidate_version"], "edge_ids": [],
            "size_bucket": strata[r["repo"]]["size_bucket"], "test_command": screens[r["repo"]],
        })
        e["edge_ids"].append(r["edge_id"])
    for e in experiments.values():
        e["edge_ids"].sort()
        e["patch_mode"], e["dep_field"] = patch_mode(pkgs[e["repo"]], e["dep_name"])
        e["experiment_id"] = f"{e['repo']}::{e['dep_name']}@{e['candidate_version']}"

    pool_by_bucket = defaultdict(lambda: defaultdict(list))
    for e in experiments.values():
        pool_by_bucket[e["size_bucket"]][e["repo"]].append(e)

    selected, shortfalls = [], {}
    for bucket, quota in ALLOCATION.items():
        by_repo = {r: sorted(v, key=lambda x: x["experiment_id"]) for r, v in pool_by_bucket[bucket].items()}
        rng = random.Random(f"{SEED}:{bucket}")
        taken = defaultdict(int)
        floor = DIRECT_FLOOR.get(bucket, 0)
        direct_by_repo = {r: [e for e in v if e["patch_mode"] == "direct_field"] for r, v in by_repo.items()}
        direct_by_repo = {r: v for r, v in direct_by_repo.items() if v}
        got = round_robin_pick(direct_by_repo, floor, rng, taken) if floor else []
        chosen = {e["experiment_id"] for e in got}
        rest = {r: [e for e in v if e["experiment_id"] not in chosen] for r, v in by_repo.items()}
        got += round_robin_pick(rest, quota - len(got), rng, taken)
        selected.extend(got)
        if len(got) < quota:
            shortfalls[bucket] = {"target": quota, "got": len(got),
                                  "note": "not backfilled from other buckets (allocation is frozen)"}
    selected.sort(key=lambda x: x["experiment_id"])

    manifest = {
        "protocol": "docs/phase3_protocol.md",
        "generated_on": datetime.date.today().isoformat(),
        "outcome_blind": True,
        "frozen_parameters": {"seed": SEED, "allocation": ALLOCATION, "per_repo_cap": PER_REPO_CAP, "direct_floor": DIRECT_FLOOR,
                              "non_hermetic_keywords": NON_HERMETIC_KEYWORDS,
                              "non_hermetic_repos": NON_HERMETIC_REPOS},
        "pool": {
            "layer1_ok_edges": len(ok),
            "unique_experiments_after_screen": len(experiments),
            "unique_experiments_by_bucket": {b: sum(len(v) for v in d.values()) for b, d in pool_by_bucket.items()},
            "repos_excluded_by_screen": excluded,
        },
        "shortfalls": shortfalls,
        "n_selected": len(selected),
        "selected": selected,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(manifest, open(OUT, "w"), indent=2, sort_keys=True)
    digest = canonical_sha256(manifest)
    open(HASH_OUT, "w").write(digest + "\n")

    print(f"[select] Layer-1 OK edges: {len(ok)}; unique experiments after screen: {len(experiments)}")
    print(f"[select] repos excluded by hermetic screen: {len(excluded)}")
    for r, why in sorted(excluded.items()):
        print(f"           - {r}: {why}")
    print(f"[select] selected {len(selected)} experiments; shortfalls: {shortfalls or 'none'}")
    by_b = defaultdict(int)
    for e in selected:
        by_b[e["size_bucket"]] += 1
    print(f"[select] by bucket: {dict(by_b)}; repos: {len({e['repo'] for e in selected})}; "
          f"patch modes: { {m: sum(1 for e in selected if e['patch_mode']==m) for m in ('direct_field','overrides')} }")
    print(f"[select] manifest sha256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
