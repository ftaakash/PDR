"""Layer 1 summary + ripple-size sensitivity (TASKS.md T2/T3)."""
import importlib.util
import os

from pdr.stats import clustered, ok_within_ripple


def _mod():
    path = os.path.join(os.path.dirname(__file__), "..", "scripts", "layer1_report.py")
    spec = importlib.util.spec_from_file_location("layer1_report", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def row(repo, outcome, n_ripple=None, applied=True, dep="x", cand="1.0.1"):
    r = {"repo": repo, "outcome": outcome, "dep_name": dep, "candidate_version": cand}
    if outcome in ("OK", "RIPPLE"):
        r.update(n_ripple=n_ripple if n_ripple is not None else 0, candidate_actually_applied=applied)
    return r


def test_ok_within_ripple_k0_is_the_frozen_definition():
    assert ok_within_ripple(row("a", "OK"), 0)
    assert not ok_within_ripple(row("a", "RIPPLE", 1), 0)
    assert ok_within_ripple(row("a", "RIPPLE", 1), 1)
    assert ok_within_ripple(row("a", "RIPPLE", 5), 5) and not ok_within_ripple(row("a", "RIPPLE", 6), 5)


def test_unapplied_candidate_and_conflicts_never_count():
    assert not ok_within_ripple(row("a", "RIPPLE", 0, applied=False), 10)
    assert not ok_within_ripple(row("a", "PEER_CONFLICT"), 10)
    assert not ok_within_ripple({"repo": "a", "outcome": "TIMEOUT"}, 10)


def test_sensitivity_is_monotone_and_concentration_on_fixture():
    rows = [row("a", "OK", dep="p"), row("a", "RIPPLE", 1, dep="q"), row("a", "RIPPLE", 7, dep="r"),
            row("b", "RIPPLE", 2), row("b", "PEER_CONFLICT"), row("c", "RIPPLE", 12)]
    out = _mod().build(rows)
    s = [out["ripple_sensitivity"]["by_k"][str(k)]["successes"] for k in (0, 1, 2, 5, 10)]
    assert s == [1, 2, 3, 3, 4]
    c = out["concentration"]
    assert c["repos_zero_ok"] == 2 and c["repos_ge50_ok"] == 0 and c["distinct_ok_substitutions"] == 1
    assert c["top3_share_pct"] == 100.0


def test_clustered_edge_and_repo_weighting_differ_as_expected():
    c = clustered({"big": [0, 90], "small": [10, 10]})
    assert c["edge_weighted_pct"] == 10.0 and c["repo_weighted_pct"] == 50.0
