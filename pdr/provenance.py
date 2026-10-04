"""
pdr.provenance
================
Ground truth for "does version V of package NAME have npm provenance" comes
from ONE place: the `dist.attestations` field on that version inside the
package's registry packument (GET https://registry.npmjs.org/<name>).

This was verified empirically against the live registry before writing this
module (not assumed from documentation):
    express@4.21.2   -> no 'attestations' key   (pre-provenance package)
    turbo@2.11.2      -> has 'attestations' key
    vite, tsx, esbuild, @changesets/cli -> has 'attestations' key
    npm@12.0.2, eslint@10.11.0 -> no 'attestations' key
This matches what `npm view <pkg>@<version> dist.attestations` and the
"Provenance" badge on npmjs.com surface, and is the same field
`npm audit signatures` (Baseline 1) reads. Using one packument fetch per
package name (not one fetch per version) keeps this to O(unique package
names) HTTP calls rather than O(edges).

KNOWN LIMITATION (declared): `dist.attestations` reflects the registry's
CURRENT record for that version. If npm ever retroactively strips or the
registry serves a mutated record, "did version V have provenance at
publish time" and "does the registry say V has provenance right now" could
in principle diverge. This module answers the second question; Kill Test 11
in the audit prompt calls this out explicitly and it is not resolved here.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Dict, Optional


REGISTRY_BASE = "https://registry.npmjs.org"
USER_AGENT = "pdr-research-pilot/0.1 (+empirical provenance-debt study)"


@dataclass
class VersionFacts:
    version: str
    has_provenance: bool
    time: Optional[str]  # ISO publish timestamp, or None if unavailable


@dataclass
class Packument:
    name: str
    found: bool
    versions: Dict[str, VersionFacts]
    error: Optional[str] = None


def _encode_name(name: str) -> str:
    # Scoped packages (@scope/name) must have the '/' percent-encoded for the
    # registry path segment.
    if name.startswith("@"):
        return name.replace("/", "%2f")
    return name


def fetch_packument(name: str, cache_dir: str, retries: int = 3, sleep: float = 0.05) -> Packument:
    os.makedirs(cache_dir, exist_ok=True)
    safe_fname = name.replace("/", "__").replace("@", "AT")
    cache_path = os.path.join(cache_dir, f"{safe_fname}.json")

    raw = None
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            raw = None

    if raw is None:
        url = f"{REGISTRY_BASE}/{_encode_name(name)}"
        last_err = None
        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    raw = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    with open(cache_path, "w", encoding="utf-8") as f:
                        json.dump({"__not_found__": True}, f)
                    return Packument(name=name, found=False, versions={}, error="404 not found")
                last_err = f"HTTP {e.code}"
                time.sleep(sleep * (attempt + 1))
            except Exception as e:  # noqa: BLE001
                last_err = str(e)
                time.sleep(sleep * (attempt + 1))
        else:
            return Packument(name=name, found=False, versions={}, error=last_err)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(raw, f)
        time.sleep(sleep)  # be polite to the public registry

    if raw.get("__not_found__"):
        return Packument(name=name, found=False, versions={}, error="404 not found (cached)")

    versions_out: Dict[str, VersionFacts] = {}
    times = raw.get("time", {}) or {}
    for v, vdata in (raw.get("versions") or {}).items():
        dist = (vdata or {}).get("dist", {}) or {}
        has_prov = "attestations" in dist
        versions_out[v] = VersionFacts(version=v, has_provenance=has_prov, time=times.get(v))

    return Packument(name=name, found=True, versions=versions_out)
