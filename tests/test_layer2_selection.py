"""
tests/test_layer2_selection.py
Layer 2 must only promote Layer-1-CONFIRMED (outcome=="OK") candidates, and
must respect each repo's pre-committed cap (docs/phase2_protocol.md
Section 4) rather than silently taking more from one repo to compensate for
another having fewer available.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.layer2_structural_install import select_candidates  # noqa: E402


def _row(repo, outcome, edge_id):
    return {"repo": repo, "outcome": outcome, "edge_id": edge_id}


def test_only_ok_outcomes_are_eligible():
    rows = [
        _row("repoA", "OK", "1"),
        _row("repoA", "RIPPLE", "2"),
        _row("repoA", "PEER_CONFLICT", "3"),
    ]
    selected, counts = select_candidates(rows, {"repoA": 5})
    assert [r["edge_id"] for r in selected] == ["1"]
    assert counts == {"repoA": 1}


def test_repo_not_in_caps_is_ignored():
    rows = [_row("repoA", "OK", "1"), _row("repoB", "OK", "2")]
    selected, counts = select_candidates(rows, {"repoA": 5})
    assert [r["edge_id"] for r in selected] == ["1"]
    assert counts == {"repoA": 1}


def test_cap_is_respected_not_exceeded():
    rows = [_row("repoA", "OK", str(i)) for i in range(10)]
    selected, counts = select_candidates(rows, {"repoA": 3})
    assert len(selected) == 3
    assert counts["repoA"] == 3


def test_shortfall_in_one_repo_is_not_compensated_by_another():
    # repoA has fewer OK candidates than its cap -- repoB's cap must stay
    # fixed at its own value, not silently absorb repoA's shortfall.
    rows = [_row("repoA", "OK", "a1")] + [_row("repoB", "OK", f"b{i}") for i in range(5)]
    selected, counts = select_candidates(rows, {"repoA": 5, "repoB": 5})
    assert counts["repoA"] == 1
    assert counts["repoB"] == 5
    assert len(selected) == 6


def test_zero_available_candidates_reports_zero_not_error():
    selected, counts = select_candidates([], {"repoA": 5, "repoB": 2})
    assert selected == []
    assert counts == {"repoA": 0, "repoB": 0}
