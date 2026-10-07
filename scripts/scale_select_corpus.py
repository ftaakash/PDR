#!/usr/bin/env python3
"""
scripts/scale_select_corpus.py   (needs GITHUB_TOKEN in the environment)

Builds the scale_v1 corpus exactly as docs/phase4_protocol.md Section 2
specifies: search-API frame in 4 star bands x {JavaScript, TypeScript},
8 strata (band x created before/after 2018-01-01), seeded visiting order,
first 20 eligible repositories per stratum. Eligible = root package-lock.json
with lockfileVersion >= 2 at the default-branch HEAD commit (SHA recorded),
plus a parseable package.json at the same SHA.

Outputs:
  configs/experiments/scale_v1.yaml                       (repos, pinned SHAs, strata)
  results/processed/scale_v1_frame.json                    (frame sizes, eligibility log; resumable)
  results/raw/provenance_scale/package_jsons/<repo>.package.json   (at the pinned SHA)
The token is read from the environment only and never printed or written.
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import yaml

SEED = 20261007
PER_STRATUM = 20
PUSHED_SINCE = "2026-04-07"
AGE_SPLIT = "2018-01-01"
BANDS = [("1k-2k", "1000..1999"), ("2k-5k", "2000..4999"), ("5k-20k", "5000..19999"), ("20k+", ">=20000")]
LANGS = ["JavaScript", "TypeScript"]
PHASE1_CONFIG = "configs/experiments/kill_v1_phase1_n45.yaml"
OUT_CONFIG = "configs/experiments/scale_v1.yaml"
FRAME = "results/processed/scale_v1_frame.json"
PKG_DIR = "results/raw/provenance_scale/package_jsons"
UA = "pdr-research-scale/0.1"


def api(url: str, accept: str = "application/vnd.github+json"):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
                                               "Accept": accept, "User-Agent": UA,
                                               "X-GitHub-Api-Version": "2022-11-28"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) and attempt < 4:      # secondary rate limit: back off
                time.sleep(30 * (attempt + 1))
                continue
            raise


def raw(repo: str, sha: str, path: str) -> bytes | None:
    url = f"https://raw.githubusercontent.com/{repo}/{sha}/{path}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def stratum_of(item: dict, band: str) -> str:
    return f"{band}|{'pre2018' if item['created_at'] < AGE_SPLIT else 'post2018'}"


def build_frame(state: dict) -> dict:
    if state.get("frame"):
        return state["frame"]
    frame = {}
    for lang in LANGS:
        for band, rng_q in BANDS:
            q = f"language:{lang} stars:{rng_q} fork:false archived:false pushed:>={PUSHED_SINCE}"
            for page in range(1, 11):
                url = ("https://api.github.com/search/repositories?" +
                       urllib.parse.urlencode({"q": q, "sort": "stars", "order": "desc",
                                               "per_page": 100, "page": page}))
                res = api(url)
                items = res.get("items") or []
                for it in items:
                    frame[it["full_name"]] = {
                        "repo": it["full_name"], "language": lang, "band": band,
                        "stars": it["stargazers_count"], "created_at": it["created_at"],
                        "pushed_at": it["pushed_at"], "default_branch": it["default_branch"],
                        "stratum": stratum_of(it, band)}
                time.sleep(2.2)                                # search API: 30 requests/minute
                if len(items) < 100:
                    break
            print(f"[frame] {lang} {band}: frame now {len(frame)}", flush=True)
    state["frame"] = frame
    return frame


def main() -> int:
    if not os.environ.get("GITHUB_TOKEN"):
        raise SystemExit("REFUSING: GITHUB_TOKEN not set in the environment")
    state = json.load(open(FRAME, encoding="utf-8")) if os.path.exists(FRAME) else {}
    phase1 = {r["repo"].lower() for r in yaml.safe_load(open(PHASE1_CONFIG))["repos"]}
    frame = build_frame(state)
    json.dump(state, open(FRAME, "w", encoding="utf-8"), indent=1)

    strata: dict = {}
    for f in frame.values():
        if f["repo"].lower() in phase1:
            continue
        strata.setdefault(f["stratum"], []).append(f)
    state["frame_sizes"] = {s: len(v) for s, v in sorted(strata.items())}
    checked = state.setdefault("checked", {})
    os.makedirs(PKG_DIR, exist_ok=True)

    selected = []
    for s in sorted(strata):
        cands = sorted(strata[s], key=lambda x: x["repo"])
        random.Random(f"{SEED}:{s}").shuffle(cands)
        kept = 0
        for c in cands:
            if kept >= PER_STRATUM:
                break
            repo = c["repo"]
            if repo not in checked:
                try:
                    sha = api(f"https://api.github.com/repos/{repo}/commits/{urllib.parse.quote(c['default_branch'])}")["sha"]
                    lock = raw(repo, sha, "package-lock.json")
                    rec = {"sha": sha}
                    if lock is None:
                        rec["eligible"], rec["reason"] = False, "no root package-lock.json"
                    else:
                        lv = json.loads(lock.decode("utf-8")).get("lockfileVersion", 0)
                        pj = raw(repo, sha, "package.json")
                        if lv < 2:
                            rec["eligible"], rec["reason"] = False, f"lockfileVersion {lv}"
                        elif pj is None:
                            rec["eligible"], rec["reason"] = False, "no package.json"
                        else:
                            pkg = json.loads(pj.decode("utf-8"))
                            json.dump(pkg, open(os.path.join(PKG_DIR, repo.replace("/", "_") + ".package.json"),
                                                "w", encoding="utf-8"))
                            rec["eligible"], rec["lockfile_bytes"], rec["lockfile_version"] = True, len(lock), lv
                except (ValueError, UnicodeDecodeError) as e:
                    rec = {"eligible": False, "reason": f"unparseable: {type(e).__name__}"}
                except urllib.error.HTTPError as e:
                    rec = {"eligible": False, "reason": f"HTTP {e.code}"}
                checked[repo] = rec
                json.dump(state, open(FRAME, "w", encoding="utf-8"), indent=1)
            if checked[repo]["eligible"]:
                kept += 1
                selected.append({**c, "sha": checked[repo]["sha"],
                                 "lockfile_version": checked[repo]["lockfile_version"]})
        print(f"[select] {s}: kept {kept}/{PER_STRATUM} (frame {len(cands)})", flush=True)
        if kept < PER_STRATUM:
            state.setdefault("shortfalls", {})[s] = kept
    json.dump(state, open(FRAME, "w", encoding="utf-8"), indent=1)

    cfg = {"_comment": "scale_v1 corpus (docs/phase4_protocol.md Section 2). Generated by "
                       "scripts/scale_select_corpus.py; refs are the commit SHAs pinned at selection.",
           "repos": [{"repo": e["repo"], "ref": e["sha"], "lockfile_path": "package-lock.json",
                      "strata": {"band": e["band"], "age": e["stratum"].split("|")[1], "stars": e["stars"],
                                 "created_at": e["created_at"], "pushed_at": e["pushed_at"],
                                 "language": e["language"], "lockfile_version": e["lockfile_version"]}}
                     for e in sorted(selected, key=lambda x: x["repo"])]}
    yaml.safe_dump(cfg, open(OUT_CONFIG, "w", encoding="utf-8"), sort_keys=False)
    print(f"[select] {len(selected)} repositories -> {OUT_CONFIG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
