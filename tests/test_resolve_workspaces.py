"""
tests/test_resolve_workspaces.py
Regression test for a real bug hit while building this pipeline: npm/cli's
actual lockfile has workspace-root entries (e.g. "workspaces/arborist")
keyed WITHOUT a "node_modules/" prefix, which the first version of
pdr/resolve.py's path-segment parser did not handle and crashed on. This
test locks in the fix with a small synthetic lockfile shaped the same way,
so it fails loudly again if anyone reverts the workspace-aware logic.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pdr.resolve import parse_lockfile  # noqa: E402


SYNTHETIC_LOCK = {
    "lockfileVersion": 3,
    "packages": {
        "": {
            "name": "root-app",
            "dependencies": {"@scope/workspace-pkg": "^1.0.0", "left-pad": "^1.0.0"},
        },
        "node_modules/@scope/workspace-pkg": {"resolved": "packages/workspace-pkg", "link": True},
        "packages/workspace-pkg": {
            "name": "@scope/workspace-pkg",
            "dependencies": {"left-pad": "^1.0.0", "nested-only": "^2.0.0"},
        },
        "packages/workspace-pkg/node_modules/nested-only": {"version": "2.3.0"},
        "node_modules/left-pad": {"version": "1.3.0"},
    },
}


def _edges_by(edges, parent_path, dep_name):
    return [e for e in edges if e.parent_path == parent_path and e.dep_name == dep_name]


def test_root_edge_to_workspace_package_is_a_link_not_a_version():
    edges = parse_lockfile("synthetic/repo", SYNTHETIC_LOCK)
    [e] = _edges_by(edges, "", "@scope/workspace-pkg")
    assert e.resolved_kind == "link"
    assert e.resolved_version is None


def test_workspace_package_own_dependency_resolves_via_root_hoist():
    edges = parse_lockfile("synthetic/repo", SYNTHETIC_LOCK)
    [e] = _edges_by(edges, "packages/workspace-pkg", "left-pad")
    assert e.resolved_kind == "registry"
    assert e.resolved_version == "1.3.0"
    assert e.resolved_path == "node_modules/left-pad"


def test_workspace_local_nested_override_is_found_before_root():
    edges = parse_lockfile("synthetic/repo", SYNTHETIC_LOCK)
    [e] = _edges_by(edges, "packages/workspace-pkg", "nested-only")
    assert e.resolved_kind == "registry"
    assert e.resolved_version == "2.3.0"
    assert e.resolved_path == "packages/workspace-pkg/node_modules/nested-only"


def test_root_dependency_still_resolves_normally():
    edges = parse_lockfile("synthetic/repo", SYNTHETIC_LOCK)
    [e] = _edges_by(edges, "", "left-pad")
    assert e.resolved_version == "1.3.0"
