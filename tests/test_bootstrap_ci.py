"""
tests/test_bootstrap_ci.py
Sanity checks for scripts/bootstrap_ci.py's Wilson score interval helper
against known reference values, so a future edit to the CI math fails
loudly rather than silently shifting Phase 1's reported confidence
intervals.
"""
import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

spec = importlib.util.spec_from_file_location(
    "bootstrap_ci", os.path.join(os.path.dirname(__file__), "..", "scripts", "bootstrap_ci.py")
)
bootstrap_ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap_ci)


def test_wilson_ci_matches_known_reference_40_of_45():
    # 40/45 = 88.89%; reference Wilson 95% CI (z=1.96) is approximately
    # [0.765, 0.952] -- matches what scripts/bootstrap_ci.py reported for
    # the Phase 1 "repos with a recoverable case" secondary statistic.
    low, high = bootstrap_ci._wilson_ci(40, 45)
    assert 0.76 < low < 0.77
    assert 0.95 < high < 0.96


def test_wilson_ci_zero_n_returns_none():
    low, high = bootstrap_ci._wilson_ci(0, 0)
    assert low is None and high is None


def test_wilson_ci_all_successes_stays_within_bounds():
    low, high = bootstrap_ci._wilson_ci(10, 10)
    assert 0.0 <= low <= 1.0
    assert 0.0 <= high <= 1.0
    assert high > low


def test_wilson_ci_widens_as_n_shrinks_for_same_proportion():
    low_small, high_small = bootstrap_ci._wilson_ci(4, 5)    # 80%, n=5
    low_big, high_big = bootstrap_ci._wilson_ci(400, 500)    # 80%, n=500
    assert (high_small - low_small) > (high_big - low_big)
