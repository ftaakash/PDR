#!/usr/bin/env python3
"""
scripts/scan_regression.py --config configs/experiments/regression_v1.yaml

SECONDARY, independently-killable (README: "Regression SECONDARY only (kill
independently)"). Scans every cached packument (from check_provenance.py --
no new network calls needed) for provenance present -> absent transitions
across a package's own version history.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pdr.provenance import Packument, VersionFacts  # noqa: E402
from pdr.regression import package_regression_status, scan_package_regressions  # noqa: E402

try:
    import yaml
except ImportError:
    yaml = None


def _load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return yaml.safe_load(text) if yaml is not None else json.loads(text)


def _load_cached_packument(cache_dir: str, name: str) -> Packument:
    safe_fname = name.replace("/", "__").replace("@", "AT")
    path = os.path.join(cache_dir, f"{safe_fname}.json")
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if raw.get("__not_found__"):
        return Packument(name=name, found=False, versions={})
    versions = {}
    times = raw.get("time", {}) or {}
    for v, vdata in (raw.get("versions") or {}).items():
        dist = (vdata or {}).get("dist", {}) or {}
        versions[v] = VersionFacts(version=v, has_provenance="attestations" in dist, time=times.get(v))
    return Packument(name=name, found=True, versions=versions)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()

    cfg = _load_config(args.config)
    cache_dir = cfg.get("packument_cache_dir", "results/raw/provenance/packuments")
    out_dir = cfg.get("out_dir", "results/processed")

    cached_files = glob.glob(os.path.join(cache_dir, "*.json"))
    print(f"[scan_regression] scanning {len(cached_files)} cached packuments in {cache_dir}")

    status_counts = {"regressed": 0, "no_regression": 0, "NA": 0}
    all_events = []
    for path in cached_files:
        raw_name = os.path.basename(path)[:-5]
        # reverse the safe-name encoding used by fetch_packument()
        name = raw_name.replace("AT", "@", 1) if raw_name.startswith("AT") else raw_name
        name = name.replace("__", "/")
        try:
            pk = _load_cached_packument(cache_dir, name)
        except Exception as e:  # noqa: BLE001
            print(f"[scan_regression]   skip {name}: {e}")
            continue
        if not pk.found:
            continue
        status = package_regression_status(pk)
        status_counts[status] += 1
        if status == "regressed":
            for ev in scan_package_regressions(pk):
                all_events.append(ev.__dict__)

    total_dated = status_counts["regressed"] + status_counts["no_regression"]
    summary = {
        "note": "SECONDARY / independently-killable. Prevalence only -- "
                "builder/source-path change enrichment NOT computed in this "
                "pilot (see pdr/regression.py docstring). NA means insufficient "
                "dated version history to say anything, and is reported "
                "separately from 'no_regression' -- these are different claims.",
        "packages_scanned": len(cached_files),
        "status_counts": status_counts,
        "regression_prevalence_pct_among_dated_packages": (
            round(100.0 * status_counts["regressed"] / total_dated, 2) if total_dated else None
        ),
        "n_regression_events": len(all_events),
    }

    os.makedirs(out_dir, exist_ok=True)
    summary_path = os.path.join(out_dir, "regression_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    events_path = os.path.join(out_dir, "regression_events.jsonl")
    with open(events_path, "w", encoding="utf-8") as f:
        for ev in all_events:
            f.write(json.dumps(ev) + "\n")

    print(f"[scan_regression] {summary}")
    print(f"[scan_regression] wrote {summary_path} and {events_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
