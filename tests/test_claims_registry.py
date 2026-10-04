"""
tests/test_claims_registry.py
Fails if any number registered in docs/claims.json no longer matches what the
raw data files produce. See scripts/check_claims.py for the rules on when a
registered value may legitimately change.
"""
import importlib.util
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
spec = importlib.util.spec_from_file_location("check_claims", os.path.join(ROOT, "scripts", "check_claims.py"))
check_claims = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_claims)


def test_registered_claims_match_data():
    expected = json.load(open(os.path.join(ROOT, "docs", "claims.json")))
    bad = check_claims.diff(expected, check_claims.compute())
    assert bad == [], "docs/claims.json out of sync with data:\n  " + "\n  ".join(bad)


def test_diff_detects_a_changed_number():
    assert check_claims.diff({"a": {"x": 1}}, {"a": {"x": 2}}) != []


def test_diff_detects_a_changed_list():
    assert check_claims.diff({"a": [1, 2]}, {"a": [1, 3]}) != []


def test_diff_float_tolerance_and_underscore_keys_ignored():
    assert check_claims.diff({"p": 4.29, "_note": "x"}, {"p": 4.2900001}) == []
    assert check_claims.diff({"p": 4.29}, {"p": 4.5}) != []


def test_diff_flags_a_missing_key():
    assert check_claims.diff({"a": 1}, {}) != []
