"""Decision logic for experiment layer1_alt_v1 (docs/phase2_protocol.md S7)."""
from pdr.layer1_alt import (ALT_EXHAUSTED, ALT_OK, DRIFT_OK, K_MAX, NO_ALTERNATIVE, RESOLUTION_TOLERANCE,
                            T_CUT, alternative_candidates, classify_npm_failure, summarise_edge)
from pdr.policy import RESOLUTION_TOLERANCE as FROZEN_TOLERANCE
from pdr.sandbox import OK, PEER_CONFLICT, RESOLUTION_FAIL, RIPPLE


def f(prov=True, sat=True, diff="patch", lt=True, time="2026-01-01T00:00:00.000Z"):
    return {"has_provenance": prov, "satisfies": sat, "diff": diff, "lt_original": lt, "time": time}


def test_tolerance_matches_frozen_policy():
    assert RESOLUTION_TOLERANCE == FROZEN_TOLERANCE
    assert K_MAX == 5 and T_CUT == "2026-09-24T00:00:00Z"


def test_order_is_preserved_descending_and_capped_at_k():
    order = [f"1.0.{i}" for i in range(9, -1, -1)]
    facts = {v: f() for v in order}
    r = alternative_candidates(order, facts)
    assert r["alternatives"] == ["1.0.9", "1.0.8", "1.0.7", "1.0.6", "1.0.5"]
    assert r["n_qualifying"] == 10


def test_each_criterion_excludes():
    order = ["1.9.0", "1.8.0", "1.7.0", "1.6.0", "1.5.0", "1.4.0", "1.3.0"]
    facts = {
        "1.9.0": f(lt=False),          # not below the original candidate
        "1.8.0": f(prov=False),        # no attestations
        "1.7.0": f(sat=False),         # outside declared range
        "1.6.0": f(diff="major"),      # outside resolution tolerance
        "1.5.0": f(diff="prepatch"),   # prerelease diff is not in the tolerance set
        "1.4.0": f(time="2026-09-24T00:00:01.000Z"),  # published after T_CUT
        "1.3.0": f(diff=None),
    }
    r = alternative_candidates(order, facts)
    assert r["alternatives"] == ["1.3.0"]
    assert r["n_excluded_by_t_cut"] == 1


def test_t_cut_boundary_inclusive_and_missing_time_excluded():
    order = ["1.0.2", "1.0.1"]
    facts = {"1.0.2": f(time="2026-09-24T00:00:00.000Z"), "1.0.1": f(time=None)}
    r = alternative_candidates(order, facts)
    assert r["alternatives"] == ["1.0.2"]
    assert r["n_excluded_by_t_cut"] == 1


def test_versions_without_facts_are_skipped():
    assert alternative_candidates(["2.0.0", "1.0.0"], {"1.0.0": f()})["alternatives"] == ["1.0.0"]


def test_npm_failure_classification():
    assert classify_npm_failure("npm error code ERESOLVE\nnpm error ERESOLVE could not resolve") == PEER_CONFLICT
    assert classify_npm_failure("npm error code EOVERRIDE") == RESOLUTION_FAIL
    assert classify_npm_failure("") == RESOLUTION_FAIL
    assert classify_npm_failure(None) == RESOLUTION_FAIL


def test_summarise_stops_at_first_ok():
    r = summarise_edge(["1.0.3", "1.0.2", "1.0.1"], {"1.0.3": RIPPLE, "1.0.2": OK}, RIPPLE)
    assert r["alt_status"] == ALT_OK and r["first_ok_index"] == 2 and r["attempts_used"] == 2
    assert r["credited"] and not r["drift"] and r["alt_outcomes"] == [RIPPLE, OK]


def test_summarise_exhausted_and_none():
    r = summarise_edge(["1.0.2", "1.0.1"], {"1.0.2": RIPPLE, "1.0.1": PEER_CONFLICT}, RIPPLE)
    assert r["alt_status"] == ALT_EXHAUSTED and r["attempts_used"] == 2 and not r["credited"]
    r = summarise_edge([], {}, PEER_CONFLICT)
    assert r["alt_status"] == NO_ALTERNATIVE and r["attempts_used"] == 0 and not r["credited"]


def test_drift_is_never_credited():
    r = summarise_edge(["1.0.1"], {"1.0.1": OK}, OK)
    assert r["status"] == DRIFT_OK and r["alt_status"] == ALT_OK and not r["credited"]


def test_incomplete_run_cannot_be_summarised():
    import pytest
    with pytest.raises(KeyError):
        summarise_edge(["1.0.2", "1.0.1"], {"1.0.2": RIPPLE}, RIPPLE)


def _report():
    import importlib.util, os
    path = os.path.join(os.path.dirname(__file__), "..", "scripts", "layer1_alt_report.py")
    spec = importlib.util.spec_from_file_location("layer1_alt_report", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_clustered_reproduces_registered_layer1_figures():
    import collections, json, os
    root = os.path.join(os.path.dirname(__file__), "..")
    rows = [json.loads(l) for l in open(os.path.join(root, "results/processed/phase2_layer1_results.jsonl"),
                                        encoding="utf-8") if l.strip()]
    claims = json.load(open(os.path.join(root, "docs/claims.json"), encoding="utf-8"))["layer1"]
    by = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        by[r["repo"]][1] += 1
        by[r["repo"]][0] += r["outcome"] == "OK"
    c = _report().clustered(by)
    assert c["edge_weighted_pct"] == claims["ok_pct_pooled"]
    assert c["edge_weighted_ci95_pct"] == claims["ok_pct_ci95_clustered"]
    assert c["repo_weighted_pct"] == claims["ok_pct_repo_macro_mean"]


def test_build_on_synthetic_fixture():
    layer1 = [
        {"edge_id": "a#1", "repo": "a", "outcome": OK},
        {"edge_id": "a#2", "repo": "a", "outcome": RIPPLE},
        {"edge_id": "b#1", "repo": "b", "outcome": RIPPLE},
        {"edge_id": "b#2", "repo": "b", "outcome": PEER_CONFLICT},
    ]
    base = {"declared_range": "^1.0.0", "resolved_version": "1.0.0"}
    plan = {"experiment_id": "layer1_alt_v1", "k_max": 5, "t_cut": T_CUT, "edges": [
        {**base, "edge_id": "a#2", "repo": "a", "dep_name": "x", "original_candidate": "1.0.9",
         "layer1_outcome": RIPPLE, "alternatives": ["1.0.8", "1.0.7"]},
        {**base, "edge_id": "b#1", "repo": "b", "dep_name": "y", "original_candidate": "1.0.9",
         "layer1_outcome": RIPPLE, "alternatives": []},
        {**base, "edge_id": "b#2", "repo": "b", "dep_name": "z", "original_candidate": "1.0.9",
         "layer1_outcome": PEER_CONFLICT, "alternatives": ["1.0.5"]},
    ]}
    attempts = [
        {"repo": "a", "dep_name": "x", "version": "1.0.9", "outcome": RIPPLE},
        {"repo": "a", "dep_name": "x", "version": "1.0.8", "outcome": RIPPLE},
        {"repo": "a", "dep_name": "x", "version": "1.0.7", "outcome": OK},
        {"repo": "b", "dep_name": "y", "version": "1.0.9", "outcome": RIPPLE},
        {"repo": "b", "dep_name": "z", "version": "1.0.9", "outcome": PEER_CONFLICT},
        {"repo": "b", "dep_name": "z", "version": "1.0.5", "outcome": PEER_CONFLICT},
    ]
    out = _report().build(layer1, plan, attempts)
    assert out["complete"]
    assert out["primary"]["single_candidate"]["successes"] == 1
    assert out["primary"]["exists_any"]["successes"] == 2
    assert out["primary"]["exists_any"]["n"] == 4
    assert out["primary"]["exists_any"]["repo_weighted_pct"] == 50.0  # a: 2/2, b: 0/2
    sec = out["secondary"]
    assert sec["no_alternative"] == 1 and sec["first_ok_index_dist"] == {2: 1}
    assert sec["attempts_used_when_exhausted_dist"] == {1: 1}
    assert sec["attempt0_concordance_edges"] == {"PEER_CONFLICT->PEER_CONFLICT": 1, "RIPPLE->RIPPLE": 2}


def test_build_flags_incomplete_runs():
    layer1 = [{"edge_id": "a#1", "repo": "a", "outcome": RIPPLE}]
    plan = {"experiment_id": "layer1_alt_v1", "k_max": 5, "t_cut": T_CUT, "edges": [
        {"edge_id": "a#1", "repo": "a", "dep_name": "x", "original_candidate": "1.0.9", "declared_range": "^1",
         "resolved_version": "1.0.0", "layer1_outcome": RIPPLE, "alternatives": ["1.0.8"]}]}
    out = _report().build(layer1, plan, [{"repo": "a", "dep_name": "x", "version": "1.0.9", "outcome": RIPPLE}])
    assert not out["complete"] and out["population_edges_missing_attempts"] == 1
