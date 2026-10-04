"""
pdr.sandbox
============
Shared taxonomy and helpers for Phase 2's layered execution
(docs/phase2_protocol.md). Only Layers 1 and 2 have runnable code in this
module -- Layer 3 is deliberately not implemented here (see
docs/phase2_protocol.md Section 5).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

USER_AGENT = "pdr-research-pilot/0.1"

# Frozen taxonomy -- docs/phase2_protocol.md Section 3. Keep in sync.
RESOLUTION_FAIL = "RESOLUTION_FAIL"
RIPPLE = "RIPPLE"
PEER_CONFLICT = "PEER_CONFLICT"
INSTALL_FAIL = "INSTALL_FAIL"
TIMEOUT = "TIMEOUT"
RESOURCE_LIMIT = "RESOURCE_LIMIT"
LIFECYCLE_FAIL = "LIFECYCLE_FAIL"   # Layer 3 only -- never produced by this session's code
TEST_FAIL = "TEST_FAIL"             # Layer 3 only -- never produced by this session's code
NO_BEHAVIORAL_CHANGE = "NO_BEHAVIORAL_CHANGE"  # Layer 3 only
OK = "OK"

ALL_OUTCOMES = [RESOLUTION_FAIL, RIPPLE, PEER_CONFLICT, INSTALL_FAIL, TIMEOUT,
                RESOURCE_LIMIT, LIFECYCLE_FAIL, TEST_FAIL, NO_BEHAVIORAL_CHANGE, OK]
LAYER3_ONLY_OUTCOMES = {LIFECYCLE_FAIL, TEST_FAIL, NO_BEHAVIORAL_CHANGE}


def fetch_text(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


class PackageJsonCache:
    """One fetch per repo, reused across every candidate from that repo --
    Layer 1 touches up to 2,349 candidates across only 40 repos, so this
    matters for both politeness to GitHub and wall-clock time."""

    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self._mem: dict = {}

    def get(self, repo: str) -> dict | None:
        if repo in self._mem:
            return self._mem[repo]
        safe = repo.replace("/", "_")
        path = os.path.join(self.cache_dir, f"{safe}.package.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._mem[repo] = data
            return data
        try:
            text = fetch_text(f"https://raw.githubusercontent.com/{repo}/HEAD/package.json")
            data = json.loads(text)
        except (urllib.error.HTTPError, json.JSONDecodeError) as e:  # noqa: BLE001
            self._mem[repo] = None
            return None
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        self._mem[repo] = data
        return data


def top_level_versions(lock: dict) -> dict:
    out = {}
    for path, entry in lock.get("packages", {}).items():
        if path.startswith("node_modules/") and "/node_modules/" not in path[len("node_modules/"):]:
            name = path[len("node_modules/"):]
            if "version" in entry:
                out[name] = entry["version"]
    return out


def load_jsonl(path: str) -> list:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def append_jsonl(path: str, record: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


# --- moved from scripts/layer1_resolution.py so the Phase 3 in-container runner
# can import it without importing a network-touching script. Behavior unchanged;
# scripts/layer1_resolution.py re-exports both names.
DEP_KIND_FIELDS = {"dependencies", "devDependencies", "peerDependencies", "optionalDependencies"}


def patch_package_json_for_candidate(pkg: dict, dep_name: str, candidate_version: str) -> dict:
    """Pure, testable decision logic (extracted so tests/test_layer1_patch_logic.py
    can lock this in without needing network or a real npm binary): given a
    repo's real package.json and a candidate substitution, return a NEW dict
    (input is never mutated) with either the direct-dependency field patched
    or an `overrides` entry added.

    npm's `overrides` field errors with EOVERRIDE whenever the target
    package name is a direct dependency of the ROOT package.json, in ANY
    dependency field -- not only when the specific edge under test is
    itself a root-level edge. (First attempt at this fix only checked
    `parent_path == ""`, which missed monorepo cases where the failing
    edge is nested/transitive but the package name is STILL also a root
    direct dependency elsewhere -- e.g. puppeteer/puppeteer's root
    devDependencies pins yargs@18.0.0 while the tested edge was
    packages/browsers's own yargs dependency. Confirmed by inspecting the
    actual npm error and the fetched package.json directly before writing
    this fix -- see docs/phase2_layer1_results.md.)
    """
    pkg = dict(pkg)  # never mutate the caller's dict (e.g. the shared PackageJsonCache entry)

    root_dep_field = None
    for field in DEP_KIND_FIELDS:
        if dep_name in (pkg.get(field) or {}):
            root_dep_field = field
            break

    if root_dep_field is not None:
        section = dict(pkg[root_dep_field])
        section[dep_name] = candidate_version
        pkg[root_dep_field] = section
    else:
        overrides = dict(pkg.get("overrides") or {})
        overrides[dep_name] = candidate_version
        pkg["overrides"] = overrides
    return pkg
