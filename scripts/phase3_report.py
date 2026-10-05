#!/usr/bin/env python3
"""
scripts/phase3_report.py [--in PATH] [--out PATH]

Pre-specified Layer 3 analysis (docs/phase3_protocol.md Section 10), written
and tested on synthetic fixtures before any real Layer 3 record existed.
Pure analysis: reads the orchestrator's JSONL, never runs anything.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pdr import phase3 as p3  # noqa: E402
from pdr.sandbox import NO_BEHAVIORAL_CHANGE, OK, load_jsonl  # noqa: E402
from pdr.stats import clustered  # noqa: E402

IN = "results/processed/phase3_micropilot_results.jsonl"
OUT = "results/processed/phase3_summary.json"
DELTA_STAGES = ("install", "lifecycle", "test")
PRIMARY = "test"
MIN_TEST_PAIRS = 10          # docs/audit_v2.md: no Gate D claim below this
B0_INVALID_REWORK = 0.30     # docs/audit_v2.md micro-pilot REWORK threshold
NBC_ADDS_NOTHING = 0.50      # docs/audit_v2.md "Layer 3 adds nothing" threshold


def b0_usable(rec: dict) -> bool:
    return p3.stage_kind(rec["b0"], "install") is None and p3.stage_ran(rec["b0"], "install") \
        and p3.b0_test_status(rec["b0"]) == "PASS"


def rate(records, pred):
    by = collections.defaultdict(lambda: [0, 0])
    for r, c in records:
        by[r["repo"]][1] += 1
        by[r["repo"]][0] += bool(pred(r, c))
    return clustered(dict(by))


def audit_summary(pairs) -> dict:
    parsed = [(r, c) for r, c in pairs if c["audit_parse_ok"]]
    d_inv, d_mis = [], []
    for r, _ in parsed:
        a, b = p3.audit_parsed(r["b0"]), p3.audit_parsed(r["pdr"])
        d_inv.append(b["invalid"] - a["invalid"])
        d_mis.append(b["missing"] - a["missing"])
    return {
        "pairs_with_audit_on_both_arms": sum(1 for _, c in pairs if c["audit_parse_ok"] is not None),
        "pairs_parse_ok": len(parsed),
        "pairs_parse_failed": sum(1 for _, c in pairs if c["audit_parse_ok"] is False),
        "audit_signature_change": sum(1 for _, c in pairs if c["outcome"] == p3.AUDIT_SIGNATURE_CHANGE),
        "invalid_delta_sum": sum(d_inv), "missing_delta_sum": sum(d_mis),
    }


def attestation_summary(pairs) -> dict:
    g = [c["attestation_gain"] for _, c in pairs if c["attestation_gain"] is not None]
    return {"n": len(g), "gain_gt0": sum(x > 0 for x in g), "gain_eq0": sum(x == 0 for x in g),
            "gain_lt0": sum(x < 0 for x in g), "median": statistics.median(g) if g else None}


def build(records: list) -> dict:
    invalid = []
    valid = []
    for i, r in enumerate(records):
        problems = p3.validate_record(r)
        if problems:
            invalid.append({"index": i, "edge_id": r.get("edge_id"), "problems": problems})
        else:
            valid.append(r)
    pairs = [(r, p3.classify_pair(r["b0"], r["pdr"])) for r in valid]   # recomputed, never trusted
    counts = collections.Counter(c["outcome"] for _, c in pairs)

    per_repo = collections.defaultdict(collections.Counter)
    for r, c in pairs:
        per_repo[r["repo"]][c["outcome"]] += 1

    deltas = {s: p3.paired_delta(valid, s) for s in DELTA_STAGES}
    n_test_pairs = deltas[PRIMARY]["n_pairs"]

    b0_invalid = sum(1 for r in valid if not b0_usable(r))
    reached_end = [(r, c) for r, c in pairs if c["failure_stage"] is None]
    nbc = sum(1 for _, c in reached_end if c["outcome"] == NO_BEHAVIORAL_CHANGE)
    usable = [(r, c) for r, c in pairs if b0_usable(r)]

    return {
        "n_records": len(records), "n_valid": len(valid), "invalid_records": invalid,
        "outcome_counts": dict(counts),
        "per_repo": {repo: dict(c) for repo, c in sorted(per_repo.items())},
        "funnel": p3.funnel(valid),
        "paired_deltas": deltas,
        "primary": {"stage": PRIMARY, **deltas[PRIMARY],
                    "underpowered": n_test_pairs < MIN_TEST_PAIRS},
        "audit": audit_summary(pairs),
        "attestation_gain": attestation_summary(pairs),
        "viability_ok_rate": {
            "all_valid": rate(pairs, lambda r, c: c["outcome"] == OK),
            "usable_baseline": rate(usable, lambda r, c: c["outcome"] == OK),
        },
        "flags": {
            "b0_invalid": b0_invalid,
            "b0_invalid_share": (b0_invalid / len(valid)) if valid else None,
            "REWORK": bool(valid) and b0_invalid / len(valid) > B0_INVALID_REWORK,
            "no_behavioral_change_share_of_completed": (nbc / len(reached_end)) if reached_end else None,
            "LAYER3_ADDS_NOTHING": bool(reached_end) and nbc / len(reached_end) > NBC_ADDS_NOTHING,
            "NO_GATE_D_CLAIM": n_test_pairs < MIN_TEST_PAIRS,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=IN)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    if not os.path.exists(a.inp):
        print(f"[phase3_report] no results at {a.inp}; nothing to report")
        return 1
    out = build(load_jsonl(a.inp))
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, default=str)
    pr = out["primary"]
    print(f"[phase3_report] {out['n_valid']}/{out['n_records']} valid; outcomes {out['outcome_counts']}")
    print(f"[phase3_report] primary test delta {pr['delta']} CI {pr['ci95']} over {pr['n_pairs']} pairs"
          + (" (UNDERPOWERED: no Gate D claim)" if pr["underpowered"] else ""))
    print(f"[phase3_report] flags {out['flags']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
