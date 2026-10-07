#!/usr/bin/env python3
"""
scripts/make_figures.py   (TASKS.md T11)

Builds every figure, table and number used by the paper FROM docs/claims.json
ONLY (which scripts/check_claims.py recomputes from raw data), so no number in
the paper can drift from the data:

  paper/figures/fig_funnel.pdf        attrition funnel, both corpora
  paper/figures/fig_forest.pdf        edge- vs repo-weighted rates with clustered CIs
  paper/figures/fig_ripple.pdf        ripple-size sensitivity (k = 0..10)
  paper/numbers.tex                   \\newcommand macros for every number in prose
  paper/tables/*.tex                  LaTeX tables

Run scripts/check_claims.py first; this script refuses to run if it fails.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PAPER = os.path.join(ROOT, "paper")
FIG, TAB = os.path.join(PAPER, "figures"), os.path.join(PAPER, "tables")
plt.rcParams.update({"font.size": 8, "font.family": "serif", "axes.spines.top": False,
                     "axes.spines.right": False, "pdf.fonttype": 42})
C1, C2, GREY = "#1f4e79", "#c55a11", "#7f7f7f"


def fmt(x, d=2):
    return f"{x:,.{d}f}" if isinstance(x, float) else f"{x:,}"


def ci(v):
    return f"[{v[0]:.1f}, {v[1]:.1f}]"


def macros(c: dict) -> str:
    s, p1, p1c, l1, alt, ls = (c["scale_v1"], c["phase1_45"], c["phase1_45_clustered"], c["layer1"],
                               c["layer1_alt_v1"], c["layer1_summary"])
    v3 = c["phase3_micropilot_v3"]
    m = {
        # Phase 1 corpus (45 repositories)
        "POneRepos": p1["repos"], "POneEdges": fmt(p1["edges"]), "POneUnknown": fmt(p1["unknown_pct"]),
        "POneOPG": fmt(p1c["opg"]["edge_weighted_pct"]), "POneOPGci": ci(p1c["opg"]["edge_weighted_ci95_pct"]),
        "POneOPGrepo": fmt(p1c["opg"]["repo_weighted_pct"], 1),
        "POneOPGrepoCi": ci(p1c["opg"]["repo_weighted_ci95_pct"]),
        "POneDeficient": fmt(p1["deficient_edges"]), "POneProxy": fmt(p1["proxy_positive_edges"]),
        "POneProxyPct": fmt(p1c["proxy_positive_among_deficient"]["edge_weighted_pct"]),
        "POneProxyCi": ci(p1c["proxy_positive_among_deficient"]["edge_weighted_ci95_pct"]),
        "POneProxyRepo": fmt(p1c["proxy_positive_among_deficient"]["repo_weighted_pct"], 1),
        "POneProxyRepoCi": ci(p1c["proxy_positive_among_deficient"]["repo_weighted_ci95_pct"]),
        "LOneOK": fmt(l1["OK"]), "LOneN": fmt(l1["n"]), "LOneRipple": fmt(l1["RIPPLE"]),
        "LOnePeer": fmt(l1["PEER_CONFLICT"]), "LOnePct": fmt(l1["ok_pct_pooled"]), "LOneCi": ci(l1["ok_pct_ci95_clustered"]),
        "LOneRepo": fmt(l1["ok_pct_repo_macro_mean"], 1), "LOneRepoCi": ci(ls["ok_pct_repo_weighted_ci95"]),
        "AltExists": fmt(alt["exists_any"]["edge_weighted_pct"]), "AltExistsCi": ci(alt["exists_any"]["edge_weighted_ci95_pct"]),
        "AltExistsRepo": fmt(alt["exists_any"]["repo_weighted_pct"], 1),
        "AltRecovered": alt["alt_ok_within_population"]["successes"], "AltPop": fmt(alt["population_edges"]),
        "AltNoAlt": fmt(alt["status_counts"]["NO_ALTERNATIVE"]),
        "AltBlocked": alt["platform_blocked_edges"],
        "RipOne": fmt(ls["ripple_sensitivity"]["1"]["edge_weighted_pct"]),
        "RipOneRepo": fmt(ls["ripple_sensitivity"]["1"]["repo_weighted_pct"], 1),
        "RipFive": fmt(ls["ripple_sensitivity"]["5"]["edge_weighted_pct"]),
        "RipFiveRepo": fmt(ls["ripple_sensitivity"]["5"]["repo_weighted_pct"], 1),
        "LTwoN": c["layer2"]["n"], "LTwoOK": c["layer2"]["pdr_install_ok"],
        "MPOK": v3["outcome_counts"].get("OK", 0), "MPInvalid": v3["b0_invalid"], "MPN": v3["n_records"],
        "MPJudge": v3["judgeable_attributable_test"],
        # scale_v1 corpus (160 repositories)
        "SRepos": s["repos"], "SEdges": fmt(s["edges"]), "SUnknown": fmt(s["unknown_pct"]),
        "SOPG": fmt(s["opg"]["edge_weighted_pct"]), "SOPGci": ci(s["opg"]["edge_weighted_ci95_pct"]),
        "SOPGrepo": fmt(s["opg"]["repo_weighted_pct"], 1), "SOPGrepoCi": ci(s["opg"]["repo_weighted_ci95_pct"]),
        "SDeficient": fmt(s["opg"]["successes"]),
        "SProxy": fmt(s["proxy_positive_among_deficient"]["successes"]),
        "SProxyPct": fmt(s["proxy_positive_among_deficient"]["edge_weighted_pct"]),
        "SProxyCi": ci(s["proxy_positive_among_deficient"]["edge_weighted_ci95_pct"]),
        "SProxyRepo": fmt(s["proxy_positive_among_deficient"]["repo_weighted_pct"], 1),
        "SProxyRepoCi": ci(s["proxy_positive_among_deficient"]["repo_weighted_ci95_pct"]),
        "SLOK": fmt(s["layer1_ok"]["successes"]), "SLPct": fmt(s["layer1_ok"]["edge_weighted_pct"]),
        "SLCi": ci(s["layer1_ok"]["edge_weighted_ci95_pct"]), "SLRepo": fmt(s["layer1_ok"]["repo_weighted_pct"], 1),
        "SLRepoCi": ci(s["layer1_ok"]["repo_weighted_ci95_pct"]),
        "SLRipple": fmt(s["layer1_outcomes"]["RIPPLE"]), "SLPeer": fmt(s["layer1_outcomes"]["PEER_CONFLICT"]),
        "SLFail": fmt(s["layer1_outcomes"].get("RESOLUTION_FAIL", 0)),
        "SEndToEnd": fmt(100 * s["layer1_ok"]["successes"] / s["opg"]["successes"]),
        "SScreened": s["screened_repos"], "STestable": s["testable_repos"],
        "STestablePct": fmt(100 * s["testable_repos"] / s["screened_repos"], 1),
        "STestableCi": ci(s["testable_wilson_ci95"]),
        "SExp": s["experiments_run"], "SJudge": s["judgeable_experiments"], "SJudgeRepos": s["judgeable_repos"],
        "SOK": s["outcome_counts"].get("OK", 0), "SLifecycle": s["outcome_counts"].get("LIFECYCLE_FAIL", 0),
        "STestFail": s["outcome_counts"].get("TEST_FAIL", 0),
        "SOKJudgePct": fmt(s["ok_among_judgeable"]["edge_weighted_pct"]),
        "SOKJudgeCi": ci(s["ok_among_judgeable"]["edge_weighted_ci95_pct"]),
        "SNewTest": s["new_failures"]["test"], "SPairsTest": s["pairs"]["test"],
        "SNewInstall": s["new_failures"]["install"], "SNewLifecycle": s["new_failures"]["lifecycle"],
        "SPairsInstall": s["pairs"]["install"],
        "SRuleThree": fmt(100 * 3 / s["judgeable_experiments"], 1),
        "SRuleThreeRepo": fmt(100 * 3 / s["judgeable_repos"], 0),
        "SGainPos": s["attestation_gain"]["gain_gt0"], "SGainN": s["attestation_gain"]["n"],
    }
    return "% generated by scripts/make_figures.py from docs/claims.json -- do not edit\n" + "".join(
        f"\\newcommand{{\\{k}}}{{{v}}}\n" for k, v in m.items())


def funnel(c):
    s, p1 = c["scale_v1"], c["phase1_45"]
    stages = ["Resolved edges", "Lacking provenance", "Screening-positive", "Resolver-confirmed (L1)"]
    sv = [s["edges"] - round(s["edges"] * s["unknown_pct"] / 100), s["opg"]["successes"],
          s["proxy_positive_among_deficient"]["successes"], s["layer1_ok"]["successes"]]
    pv = [p1["edges"] - round(p1["edges"] * p1["unknown_pct"] / 100), p1["deficient_edges"],
          p1["proxy_positive_edges"], c["layer1"]["OK"]]
    fig, ax = plt.subplots(figsize=(3.45, 2.0))
    y = list(range(len(stages)))[::-1]
    ax.barh([i + 0.18 for i in y], sv, height=0.34, color=C1, label=f"scale_v1 ({s['repos']} repos)")
    ax.barh([i - 0.18 for i in y], pv, height=0.34, color=C2, label=f"Phase 1 ({p1['repos']} repos)")
    ax.set_xscale("log")
    ax.set_yticks(y)
    ax.set_yticklabels(stages)
    for i, (a, b) in zip(y, zip(sv, pv)):
        ax.text(a * 1.1, i + 0.18, f"{a:,}", va="center", fontsize=6.5)
        ax.text(b * 1.1, i - 0.18, f"{b:,}", va="center", fontsize=6.5)
    ax.set_xlabel("dependency edges (log scale)")
    ax.set_xlim(300, 3e6)
    ax.legend(frameon=False, fontsize=6.5, loc="lower center", bbox_to_anchor=(0.3, 1.0), ncol=2)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig_funnel.pdf")); fig.savefig(os.path.join(FIG, "fig_funnel.png"), dpi=200)


def forest(c):
    s, p1c, l1, ls = c["scale_v1"], c["phase1_45_clustered"], c["layer1"], c["layer1_summary"]
    rows = [
        ("OPG", "Phase 1", p1c["opg"]), ("OPG", "scale_v1", s["opg"]),
        ("Screening-positive", "Phase 1", p1c["proxy_positive_among_deficient"]),
        ("Screening-positive", "scale_v1", s["proxy_positive_among_deficient"]),
        ("Layer 1 OK", "Phase 1", {"edge_weighted_pct": l1["ok_pct_pooled"], "edge_weighted_ci95_pct": l1["ok_pct_ci95_clustered"],
                                   "repo_weighted_pct": l1["ok_pct_repo_macro_mean"], "repo_weighted_ci95_pct": ls["ok_pct_repo_weighted_ci95"]}),
        ("Layer 1 OK", "scale_v1", s["layer1_ok"]),
    ]
    fig, ax = plt.subplots(figsize=(3.45, 2.3))
    labels = []
    for i, (q, corp, v) in enumerate(rows):
        y = len(rows) - 1 - i
        for off, key, col, mk in ((0.15, "edge", C1, "o"), (-0.15, "repo", C2, "s")):
            m, (lo, hi) = v[f"{key}_weighted_pct"], v[f"{key}_weighted_ci95_pct"]
            ax.errorbar(m, y + off, xerr=[[m - lo], [hi - m]], fmt=mk, color=col, ms=3, capsize=2, lw=0.8,
                        label=("edge-weighted" if key == "edge" else "repo-weighted") if i == 0 else None)
        labels.append(f"{q} ({corp})")
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(labels[::-1], fontsize=6.5)
    ax.set_xlabel("percent, 95% repository-clustered CI")
    ax.set_xlim(0, 100)
    ax.legend(frameon=False, fontsize=6.5, loc="center right")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig_forest.pdf")); fig.savefig(os.path.join(FIG, "fig_forest.png"), dpi=200)


def ripple(c):
    rs = c["layer1_summary"]["ripple_sensitivity"]
    ks = sorted(rs, key=int)
    fig, ax = plt.subplots(figsize=(3.45, 1.8))
    for key, col, mk, lab in (("edge", C1, "o", "edge-weighted"), ("repo", C2, "s", "repo-weighted")):
        m = [rs[k][f"{key}_weighted_pct"] for k in ks]
        lo = [rs[k][f"{key}_weighted_ci95_pct"][0] for k in ks]
        hi = [rs[k][f"{key}_weighted_ci95_pct"][1] for k in ks]
        x = [int(k) for k in ks]
        ax.plot(x, m, marker=mk, color=col, ms=3, lw=1, label=lab)
        ax.fill_between(x, lo, hi, color=col, alpha=0.15, lw=0)
    ax.set_xlabel("other top-level packages allowed to change (k)")
    ax.set_ylabel("Layer 1 OK (%)")
    ax.set_ylim(0, 100)
    ax.set_xticks([int(k) for k in ks])
    ax.legend(frameon=False, fontsize=6.5)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "fig_ripple.pdf")); fig.savefig(os.path.join(FIG, "fig_ripple.png"), dpi=200)


def tables(c):
    s = c["scale_v1"]
    v = {k: c[k]["outcome_counts"] for k in ("phase3_micropilot", "phase3_micropilot_v2", "phase3_micropilot_v3")}
    outs = ["OK", "TEST_FAIL", "TEST_FLAKY", "TIMEOUT", "LIFECYCLE_FAIL", "INSTALL_FAIL"]
    t = ["\\begin{tabular}{lrrrr}", "\\toprule", "Outcome & MP v1 & MP v2 & MP v3 & scale\\_v1 \\\\", "\\midrule"]
    for o in outs:
        t.append(f"\\texttt{{{o.replace('_', chr(92) + '_')}}} & " + " & ".join(
            str(x.get(o, 0)) for x in (*v.values(), s["outcome_counts"])) + " \\\\")
    t.append("\\midrule")
    t.append("Invalid baselines & " + " & ".join(str(c[k]["b0_invalid"]) for k in v) +
             f" & {s['screened_repos'] - s['testable_repos']} of {s['screened_repos']} repos$^\\dagger$ \\\\")
    t.append("Experiments & " + " & ".join(str(c[k]["n_records"]) for k in v) + f" & {s['experiments_run']} \\\\")
    t += ["\\bottomrule", "\\end{tabular}"]
    open(os.path.join(TAB, "tab_layer3.tex"), "w").write("\n".join(t) + "\n")
    l1, so = c["layer1"], s["layer1_outcomes"]
    t = ["\\begin{tabular}{lrr}", "\\toprule", "Layer 1 outcome & Phase 1 & scale\\_v1 \\\\", "\\midrule"]
    for o in ("OK", "RIPPLE", "PEER_CONFLICT", "RESOLUTION_FAIL"):
        t.append(f"\\texttt{{{o.replace('_', chr(92) + '_')}}} & {l1.get(o, 0):,} & {so.get(o, 0):,} \\\\")
    t.append(f"Total & {l1['n']:,} & {sum(so.values()):,} \\\\")
    t += ["\\bottomrule", "\\end{tabular}"]
    open(os.path.join(TAB, "tab_layer1.tex"), "w").write("\n".join(t) + "\n")


def main() -> int:
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "check_claims.py")], capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout)
        raise SystemExit("REFUSING: claims check fails; figures would not match the data")
    c = json.load(open(os.path.join(ROOT, "docs", "claims.json"), encoding="utf-8"))
    os.makedirs(FIG, exist_ok=True)
    os.makedirs(TAB, exist_ok=True)
    open(os.path.join(PAPER, "numbers.tex"), "w", encoding="utf-8").write(macros(c))
    funnel(c)
    forest(c)
    ripple(c)
    tables(c)
    print("[make_figures] wrote paper/numbers.tex, 3 figures, 2 tables")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
