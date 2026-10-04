#!/usr/bin/env python3
"""
scripts/check_provenance.py --in results/raw/resolve/ --out results/raw/provenance/edges.csv

Reads every *.edges.jsonl produced by fetch_corpus.py, fetches ONE registry
packument per unique dependency name (cached to disk so re-runs are free),
classifies every edge with pdr.policy, and writes a flat CSV plus a
per-package packument cache under results/raw/provenance/packuments/.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pdr.provenance import fetch_packument  # noqa: E402
from pdr.policy import classify_edges  # noqa: E402
from pdr.resolve import Edge  # noqa: E402


def _load_edges(in_dir: str):
    edges = []
    for path in sorted(glob.glob(os.path.join(in_dir, "*.edges.jsonl"))):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                edges.append(Edge(**d))
    return edges


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_dir", required=True)
    ap.add_argument("--out", dest="out_csv", required=True)
    args = ap.parse_args()

    edges = _load_edges(args.in_dir)
    print(f"[check_provenance] loaded {len(edges)} edges from {args.in_dir}")

    dep_names = sorted({e.dep_name for e in edges})
    print(f"[check_provenance] {len(dep_names)} unique dependency names -> "
          f"1 registry packument fetch each (cached)")

    cache_dir = os.path.join(os.path.dirname(args.out_csv), "packuments")
    packuments = {}
    t0 = time.time()
    n_found = 0
    n_done = 0
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(fetch_packument, name, cache_dir): name for name in dep_names}
        for fut in as_completed(futures):
            name = futures[fut]
            pk = fut.result()
            packuments[name] = pk
            n_done += 1
            if pk.found:
                n_found += 1
            if n_done % 200 == 0 or n_done == len(dep_names):
                elapsed = time.time() - t0
                print(f"[check_provenance]   {n_done}/{len(dep_names)} packuments "
                      f"({n_found} found, {elapsed:.0f}s elapsed)")

    print(f"[check_provenance] classifying {len(edges)} edges ...")
    classifications = classify_edges(edges, packuments)

    os.makedirs(os.path.dirname(args.out_csv), exist_ok=True)
    with open(args.out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "repo", "parent_path", "parent_name", "dep_name", "declared_range",
            "dep_kind", "is_dev", "is_optional", "is_peer", "depth",
            "resolved_kind", "resolved_version", "resolved_time", "state", "candidate_version", "reason",
        ])
        for c in classifications:
            e = c.edge
            w.writerow([
                e.repo, e.parent_path, e.parent_name, e.dep_name, e.declared_range,
                e.dep_kind, e.is_dev, e.is_optional, e.is_peer, e.depth,
                e.resolved_kind, e.resolved_version, c.resolved_time or "", c.state, c.candidate_version or "", c.reason,
            ])

    print(f"[check_provenance] wrote {len(classifications)} classified edges -> {args.out_csv}")

    # Also persist the packument facts (needed by scan_regression.py without re-fetching).
    pk_index_path = os.path.join(os.path.dirname(args.out_csv), "packument_index.json")
    with open(pk_index_path, "w", encoding="utf-8") as f:
        json.dump(sorted([n for n, pk in packuments.items() if pk.found]), f)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
