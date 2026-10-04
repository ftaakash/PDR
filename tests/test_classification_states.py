"""
tests/test_classification_states.py
Verifies pdr.policy.classify_edges produces exactly the 5-state+unknown
taxonomy declared in pdr/policy.py's module docstring, using synthetic
edges/packuments so this test needs no network access. Semver range
questions still go through the real Node semver_client (local computation,
no network) -- we do not re-approximate npm range semantics in the test
fixtures either.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pdr.policy import (  # noqa: E402
    classify_edges, STATE_PROVENANCED, STATE_UNRECOVERABLE,
    STATE_SEMANTIC_ONLY, STATE_RESOLUTION_PRESERVING, STATE_UNKNOWN, ALL_STATES,
)
from pdr.provenance import Packument, VersionFacts  # noqa: E402
from pdr.resolve import Edge  # noqa: E402


def _edge(dep_name="foo", range_="^1.0.0", resolved_version="1.0.0", resolved_kind="registry", **kw):
    defaults = dict(
        repo="synthetic/repo", parent_path="", parent_name="<root>",
        dep_name=dep_name, declared_range=range_, dep_kind="dependencies",
        resolved_path=f"node_modules/{dep_name}", resolved_version=resolved_version,
        resolved_kind=resolved_kind, is_dev=False, is_optional=False, is_peer=False, depth=0,
    )
    defaults.update(kw)
    return Edge(**defaults)


def _pk(name, versions):
    """versions: dict of version -> (has_provenance, time)"""
    vf = {v: VersionFacts(version=v, has_provenance=hp, time=t) for v, (hp, t) in versions.items()}
    return Packument(name=name, found=True, versions=vf)


def test_five_states_plus_unknown_exhaustive():
    assert set(ALL_STATES) == {
        STATE_PROVENANCED, STATE_UNRECOVERABLE, STATE_SEMANTIC_ONLY,
        STATE_RESOLUTION_PRESERVING, STATE_UNKNOWN,
    }
    assert len(ALL_STATES) == 5


def test_provenanced_resolved_version():
    e = _edge(resolved_version="1.2.0")
    pk = _pk("foo", {"1.2.0": (True, "2024-01-01T00:00:00.000Z")})
    [c] = classify_edges([e], {"foo": pk})
    assert c.state == STATE_PROVENANCED


def test_unrecoverable_no_provenanced_version_anywhere():
    e = _edge(resolved_version="1.0.0", range_="^1.0.0")
    pk = _pk("foo", {"1.0.0": (False, "2020-01-01T00:00:00.000Z"),
                      "1.5.0": (False, "2020-06-01T00:00:00.000Z")})
    [c] = classify_edges([e], {"foo": pk})
    assert c.state == STATE_UNRECOVERABLE


def test_unrecoverable_provenanced_version_exists_but_out_of_range():
    e = _edge(resolved_version="1.0.0", range_="^1.0.0")
    pk = _pk("foo", {"1.0.0": (False, "2020-01-01T00:00:00.000Z"),
                      "2.0.0": (True, "2024-01-01T00:00:00.000Z")})  # major bump, out of ^1.0.0
    [c] = classify_edges([e], {"foo": pk})
    assert c.state == STATE_UNRECOVERABLE


def test_resolution_preserving_when_candidate_is_minor_bump_in_range():
    e = _edge(resolved_version="1.0.0", range_="^1.0.0")
    pk = _pk("foo", {"1.0.0": (False, "2020-01-01T00:00:00.000Z"),
                      "1.4.0": (True, "2024-01-01T00:00:00.000Z")})
    [c] = classify_edges([e], {"foo": pk})
    assert c.state == STATE_RESOLUTION_PRESERVING
    assert c.candidate_version == "1.4.0"


def test_semantic_only_when_in_range_but_outside_tolerance():
    # ">=1.0.0 <9.0.0" is wide enough that an in-range provenanced version can
    # still be a major-version jump away from what's actually resolved.
    e = _edge(resolved_version="1.0.0", range_=">=1.0.0 <9.0.0")
    pk = _pk("foo", {"1.0.0": (False, "2020-01-01T00:00:00.000Z"),
                      "8.9.0": (True, "2024-01-01T00:00:00.000Z")})
    [c] = classify_edges([e], {"foo": pk})
    assert c.state == STATE_SEMANTIC_ONLY
    assert c.candidate_version == "8.9.0"


def test_unknown_for_non_registry_resolution():
    e = _edge(resolved_kind="link", resolved_version=None)
    [c] = classify_edges([e], {})
    assert c.state == STATE_UNKNOWN


def test_unknown_for_missing_packument():
    e = _edge(dep_name="ghost-package")
    [c] = classify_edges([e], {})  # no packument for ghost-package
    assert c.state == STATE_UNKNOWN


def test_unknown_for_resolved_version_missing_from_packument():
    # can happen if the registry unpublished/removed a version after the
    # lockfile pinned it
    e = _edge(resolved_version="9.9.9")
    pk = _pk("foo", {"1.0.0": (True, "2024-01-01T00:00:00.000Z")})
    [c] = classify_edges([e], {"foo": pk})
    assert c.state == STATE_UNKNOWN
