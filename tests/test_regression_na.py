"""
tests/test_regression_na.py
README tests/ requirement: "regression NA handling". A package with fewer
than two dated versions cannot say anything about whether provenance ever
regressed -- that must come back as "NA", never silently coerced into
"no_regression" (which is a different, stronger claim).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pdr.provenance import Packument, VersionFacts  # noqa: E402
from pdr.regression import package_regression_status, scan_package_regressions  # noqa: E402


def _pk(versions):
    vf = {v: VersionFacts(version=v, has_provenance=hp, time=t) for v, (hp, t) in versions.items()}
    return Packument(name="pkg", found=True, versions=vf)


def test_zero_dated_versions_is_na():
    pk = _pk({"1.0.0": (True, None)})  # no publish time at all
    assert package_regression_status(pk) == "NA"


def test_one_dated_version_is_na():
    pk = _pk({"1.0.0": (True, "2024-01-01T00:00:00.000Z")})
    assert package_regression_status(pk) == "NA"


def test_two_dated_versions_stable_is_no_regression_not_na():
    pk = _pk({
        "1.0.0": (True, "2024-01-01T00:00:00.000Z"),
        "1.1.0": (True, "2024-02-01T00:00:00.000Z"),
    })
    assert package_regression_status(pk) == "no_regression"


def test_present_to_absent_transition_is_regressed():
    pk = _pk({
        "1.0.0": (True, "2024-01-01T00:00:00.000Z"),
        "1.1.0": (False, "2024-02-01T00:00:00.000Z"),
    })
    assert package_regression_status(pk) == "regressed"
    events = scan_package_regressions(pk)
    assert len(events) == 1
    assert events[0].from_version == "1.0.0"
    assert events[0].to_version == "1.1.0"


def test_absent_to_present_is_not_a_regression():
    pk = _pk({
        "1.0.0": (False, "2024-01-01T00:00:00.000Z"),
        "1.1.0": (True, "2024-02-01T00:00:00.000Z"),
    })
    assert package_regression_status(pk) == "no_regression"


def test_mixed_dated_and_undated_versions_ignores_undated():
    # a version with no publish time can't be placed in the chronology, so
    # it must be excluded from the walk rather than crashing or sorting
    # arbitrarily.
    pk = _pk({
        "1.0.0": (True, "2024-01-01T00:00:00.000Z"),
        "1.0.5-unlisted": (False, None),
        "1.1.0": (False, "2024-02-01T00:00:00.000Z"),
    })
    assert package_regression_status(pk) == "regressed"
    events = scan_package_regressions(pk)
    assert len(events) == 1
    assert events[0].to_version == "1.1.0"
