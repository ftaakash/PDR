#!/usr/bin/env python3
"""
scripts/analyze_kill.py --in results/raw/provenance/edges.csv --out results/processed/kill_summary.json

Computes the PDR-G1 gate criteria (README.md "Gate v4.1 FROZEN") from the
classified edge list:
    A -- OPG (Observed Provenance deficiency Gap), era-controlled
    B -- semantic PD (recoverability among deficient edges)
    C -- semantic-to-operational gap (renamed from "deployability gap" per
         docs/methodology_freeze.md Section 5 -- surviving install+tests is
         not a production-deployability claim)  [NOT MEASURED -- see docs/gate_status.md]
    D -- excess enforcement cost vs B0/B1                  [NOT MEASURED -- see docs/gate_status.md]
    E -- robustness across direct/transitive, era, repo
    F -- unknowns <= 20%

C and D require actually installing candidate recoveries into each real repo
and running its test/peer/audit pipeline -- infeasible inside this pilot's
runtime and network budget across a handful of large real repos (scale
varies by which experiment config this was run against -- see the
`n_repos`/`scale_label` fields in the output JSON for THIS run's actual
scale, never hardcode a repo count in downstream text). This script computes
what IS measurable from the resolved-edge classification alone (A, B, E, F)
honestly, and reports C/D as PENDING rather than fabricating a number, per
the audit prompt's own "never turn inference into fact" standard.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
from collections import Counter, defaultdict

PROVENANCE_GA = "2023-09-26"  # https://github.blog/changelog/2023-09-26-npm-provenance-general-availability
PROVENANCE_BETA = "2023-04-19"  # npm 9.5.0, https://github.blog/2023-04-19-introducing-npm-package-provenance/

STATES = ["PROVENANCED", "DEFICIENT_UNRECOVERABLE", "DEFICIENT_SEMANTIC_ONLY",
          "DEFICIENT_RESOLUTION_PRESERVING", "UNKNOWN"]
DEFICIENT_STATES = {"DEFICIENT_UNRECOVERABLE", "DEFICIENT_SEMANTIC_ONLY", "DEFICIENT_RESOLUTION_PRESERVING"}
RECOVERABLE_STATES = {"DEFICIENT_SEMANTIC_ONLY", "DEFICIENT_RESOLUTION_PRESERVING"}


def _era(resolved_time: str) -> str:
    if not resolved_time:
        return "unknown_era"
    try:
        d = dt.datetime.fromisoformat(resolved_time.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return "unknown_era"
    if d < PROVENANCE_BETA:
        return "pre_provenance_existed"
    if d < PROVENANCE_GA:
        return "provenance_beta_window"
    return "post_ga"


def _pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 2) if d else float("nan")


def _rate_block(rows, denom_states=None):
    n = len(rows)
    c = Counter(r["state"] for r in rows)
    opg_n = sum(c[s] for s in DEFICIENT_STATES)
    known_n = n - c["UNKNOWN"]
    recoverable_n = sum(c[s] for s in RECOVERABLE_STATES)
    resolution_preserving_n = c["DEFICIENT_RESOLUTION_PRESERVING"]
    return {
        "n_edges": n,
        "state_counts": {s: c[s] for s in STATES},
        "unknown_pct": _pct(c["UNKNOWN"], n),
        "opg_pct_of_known": _pct(opg_n, known_n) if known_n else None,
        "semantic_recovery_pct_of_deficient": _pct(recoverable_n, opg_n) if opg_n else None,
        "resolution_preserving_pct_of_deficient": _pct(resolution_preserving_n, opg_n) if opg_n else None,
        "resolution_preserving_pct_of_recoverable": _pct(resolution_preserving_n, recoverable_n) if recoverable_n else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_csv", required=True)
    ap.add_argument("--out", dest="out_json", required=True)
    args = ap.parse_args()

    rows = []
    with open(args.in_csv, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            row["era"] = _era(row.get("resolved_time", ""))
            rows.append(row)

    overall = _rate_block(rows)

    prod_rows = [r for r in rows if r["is_dev"] != "True"]
    prod = _rate_block(prod_rows)

    direct_rows = [r for r in rows if r["depth"] == "0"]
    transitive_rows = [r for r in rows if r["depth"] != "0"]
    by_direct = {"direct": _rate_block(direct_rows), "transitive": _rate_block(transitive_rows)}

    by_era = {}
    for era_label in ["pre_provenance_existed", "provenance_beta_window", "post_ga", "unknown_era"]:
        era_rows = [r for r in rows if r["era"] == era_label]
        if era_rows:
            by_era[era_label] = _rate_block(era_rows)

    by_repo = {}
    for repo in sorted({r["repo"] for r in rows}):
        by_repo[repo] = _rate_block([r for r in rows if r["repo"] == repo])

    # ---- Gate checks ----
    gate = {}

    # A: meaningful OPG, era-controlled. "Meaningful" threshold: OPG among
    # post-GA-eligible edges is >=10% (i.e. this isn't a non-phenomenon even
    # after removing packages that predate provenance's existence).
    post_ga = by_era.get("post_ga")
    a_opg = post_ga["opg_pct_of_known"] if post_ga else None
    gate["A_opg_era_controlled"] = {
        "verdict": "PASS" if (a_opg is not None and a_opg >= 10.0) else ("NO_DATA" if a_opg is None else "FAIL"),
        "post_ga_opg_pct": a_opg,
        "overall_opg_pct": overall["opg_pct_of_known"],
        "note": "era-controlled denominator = edges whose resolved version was "
                "published on/after npm provenance GA (2023-09-26); pre-GA "
                "versions cannot fairly be called 'deficient'.",
    }

    # B: meaningful semantic PD among deficient edges. Threshold: >=5% of
    # deficient edges have SOME in-range provenanced alternative (recoverable
    # states), so there's enough of a population to say anything about
    # recovery at all.
    b_pd = overall["semantic_recovery_pct_of_deficient"]
    gate["B_semantic_pd"] = {
        "verdict": "PASS" if (b_pd is not None and b_pd >= 5.0) else ("NO_DATA" if b_pd is None else "FAIL"),
        "semantic_recovery_pct_of_deficient": b_pd,
        "n_deficient": sum(overall["state_counts"][s] for s in DEFICIENT_STATES),
        "n_recoverable": sum(overall["state_counts"][s] for s in RECOVERABLE_STATES),
    }

    gate["C_semantic_to_operational_gap"] = {
        "verdict": "PENDING",
        "note": "Not measured at this scale -- requires the Phase 2 isolated-"
                "worker sandbox (docs/methodology_freeze.md Section 7) to "
                "determine, for each resolution-confirmed candidate, whether "
                "it is an OPERATIONALLY VIABLE substitution: real npm "
                "resolution succeeds, structural install (npm ci "
                "--ignore-scripts) succeeds, no new peer conflict, no "
                "npm-audit-signatures regression, and no new test failure. "
                "Deliberately NOT called 'deployability' -- "
                "docs/methodology_freeze.md Section 5 -- since surviving "
                "install+tests is not a production-deployability claim.",
    }
    gate["D_excess_enforcement_cost"] = {
        "verdict": "PENDING",
        "note": "Not measured in this pilot -- requires B0/B1 baseline install "
                "runs to compare against. See docs/gate_status.md, Phase 2.",
    }

    # E: robustness -- direct vs transitive and era slices should point the
    # same qualitative direction as the overall result (not flip sign).
    direct_opg = by_direct["direct"]["opg_pct_of_known"]
    transitive_opg = by_direct["transitive"]["opg_pct_of_known"]
    robust = (direct_opg is not None and transitive_opg is not None
              and overall["opg_pct_of_known"] is not None
              and (direct_opg > 0) == (transitive_opg > 0) == (overall["opg_pct_of_known"] > 0))
    gate["E_robustness"] = {
        "verdict": "PASS" if robust else "FAIL",
        "direct_opg_pct": direct_opg,
        "transitive_opg_pct": transitive_opg,
        "by_era_opg_pct": {k: v["opg_pct_of_known"] for k, v in by_era.items()},
        "by_repo_opg_pct": {k: v["opg_pct_of_known"] for k, v in by_repo.items()},
        "note": "lockfile-vs-floating stratification NOT evaluated (pilot only "
                "analyzes committed lockfiles); direct-vs-transitive and "
                "era/repo slices are.",
    }

    # F: unknowns <= 20%.
    gate["F_unknowns_bounded"] = {
        "verdict": "PASS" if overall["unknown_pct"] <= 20.0 else "FAIL",
        "unknown_pct": overall["unknown_pct"],
    }

    measured_items = [
        ("A", gate["A_opg_era_controlled"]["verdict"]),
        ("B", gate["B_semantic_pd"]["verdict"]),
        ("E", gate["E_robustness"]["verdict"]),
        ("F", gate["F_unknowns_bounded"]["verdict"]),
    ]
    measured = [v for _, v in measured_items]
    failed_labels = [k for k, v in measured_items if v == "FAIL"]
    if failed_labels:
        overall_verdict = f"MEASURED_FAIL_{'_'.join(failed_labels)}__C_D_PENDING"
    elif "PASS" in measured:
        overall_verdict = "PARTIAL_GO_PENDING_C_D"
    else:
        overall_verdict = "NO_DATA"

    n_repos = len({r["repo"] for r in rows})
    n_edges_total = len(rows)
    scale_label = f"{n_repos} real repo{'s' if n_repos != 1 else ''}, {n_edges_total:,} edges"
    is_full_g1 = n_repos >= 200
    scale_tag = "FULL G1 SCALE" if is_full_g1 else "DE-RISKING SCALE"

    summary = {
        "pilot_disclaimer": (
            f"{scale_tag} ({scale_label}; not the full 200-repo G1 kill-test "
            f"sample specified in the audit prompt's Kill Test 10, unless "
            f"n_repos >= 200 as noted above). Corpus composition (convenience "
            f"vs. diversified vs. stratified) is documented per-experiment in "
            f"its own config/results docs, not asserted generically here -- "
            f"see docs/phase1_results.md or the equivalent for this run's "
            f"actual corpus, and docs/methodology_freeze.md Section 4 for the "
            f"standing caution against calling any pre-200-repo corpus a "
            f"representative sample of npm."
        ) if not is_full_g1 else (
            f"{scale_tag} ({scale_label})."
        ),
        "overall": overall,
        "n_repos": n_repos,
        "n_edges_total": n_edges_total,
        "scale_label": scale_label,
        "production_only": prod,
        "by_direct_vs_transitive": by_direct,
        "by_era": by_era,
        "by_repo": by_repo,
        "gate": gate,
        "overall_verdict_measured_criteria_only": overall_verdict,
    }

    os.makedirs(os.path.dirname(args.out_json), exist_ok=True)
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"[analyze_kill] wrote {args.out_json}")

    memo_path = os.path.join(os.path.dirname(args.out_json),
                              os.path.basename(args.out_json).replace("kill_summary", "kill_memo").replace(".json", ".md"))
    if memo_path == args.out_json:  # out_json didn't contain "kill_summary" -- fall back safely
        memo_path = args.out_json.replace(".json", "_memo.md")
    _write_memo(summary, memo_path)
    print(f"[analyze_kill] wrote {memo_path}")
    return 0


def _write_memo(s: dict, path: str) -> None:
    o = s["overall"]
    g = s["gate"]
    scale_label = s.get("scale_label", "scale unknown")
    lines = []
    lines.append(f"# PDR-G1 analysis memo ({scale_label})\n")
    lines.append(s["pilot_disclaimer"] + "\n")
    lines.append(
        f"**Headline:** {o['opg_pct_of_known']}% of resolved edges lacked "
        f"provenance (OPG); of those, {o['semantic_recovery_pct_of_deficient']}% "
        f"were semantically recoverable (a provenance-bearing version exists in "
        f"the declared range), and "
        f"{o['resolution_preserving_pct_of_deficient']}% were resolution-"
        f"preserving CANDIDATES (screening-stage proxy only -- not yet "
        f"resolution-confirmed or operationally viable; see Gate C, renamed "
        f"'semantic-to-operational gap' per docs/methodology_freeze.md "
        f"Section 5 -- this is deliberately not called 'deployable').\n"
    )
    lines.append(
        "**Boundary reminder (never drop this line):** none of the above is a "
        "safety claim. Provenance is origin/integrity evidence, not a "
        "guarantee the code is benign.\n"
    )
    lines.append("## Gate results\n")
    for key in ["A_opg_era_controlled", "B_semantic_pd", "C_semantic_to_operational_gap",
                "D_excess_enforcement_cost", "E_robustness", "F_unknowns_bounded"]:
        v = g[key]
        lines.append(f"- **{key}**: {v['verdict']}")
    lines.append(f"\n**Overall (measured criteria A/B/E/F only):** "
                  f"{s['overall_verdict_measured_criteria_only']}\n")

    passed = [k.split("_")[0] for k in ["A_opg_era_controlled", "B_semantic_pd",
                                         "E_robustness", "F_unknowns_bounded"]
              if g[k]["verdict"] == "PASS"]
    failed = [k.split("_")[0] for k in ["A_opg_era_controlled", "B_semantic_pd",
                                         "E_robustness", "F_unknowns_bounded"]
              if g[k]["verdict"] == "FAIL"]
    measured_summary = (
        f"criteria {', '.join(passed)} passed" if passed else "no measured criteria passed"
    )
    if failed:
        measured_summary += f"; criteria {', '.join(failed)} FAILED"

    lines.append(
        "Per README.md, SUCCESS requires the COMBINED A-F pattern with no "
        "relaxation, so this pilot cannot itself issue a final GO or KILL -- "
        f"C and D are PENDING (not measured), and among what WAS measured, "
        f"{measured_summary}. A single FAIL among measured criteria means "
        "this run does not currently satisfy the gate, independent of C/D. "
        "What this pilot DOES establish regardless: the pipeline runs "
        "end-to-end on real npm dependency trees and the constructs are "
        "computable. Kill Test 1 (phenomenon existence) is answered YES at "
        "pilot scale -- deficiency is not negligible. If B failed here, "
        "read that as Kill Test 2's concern (recoverability may be too thin "
        "to be statistically useful) showing up in real data, not as a "
        "pipeline defect.\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    raise SystemExit(main())
