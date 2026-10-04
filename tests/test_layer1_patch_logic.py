"""
tests/test_layer1_patch_logic.py
Regression test for the EOVERRIDE bug found and fixed while running Layer 1
at full scale (docs/phase2_layer1_results.md): a package that is a direct
dependency of the root package.json in ANY field must be patched directly,
not via `overrides`, even when the specific edge under test is a
nested/transitive one -- otherwise npm's real resolver rejects the override
with EOVERRIDE. Pure logic, no network or npm binary needed.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.layer1_resolution import patch_package_json_for_candidate  # noqa: E402


def test_direct_dependency_is_patched_in_place_not_via_overrides():
    pkg = {"name": "root", "dependencies": {"yargs": "^18.0.0"}}
    out = patch_package_json_for_candidate(pkg, "yargs", "18.2.0")
    assert out["dependencies"]["yargs"] == "18.2.0"
    assert "overrides" not in out


def test_devdependency_field_is_detected_too():
    # the exact real-world case that caused the bug: puppeteer/puppeteer
    # pins yargs in devDependencies, not dependencies.
    pkg = {"name": "root", "devDependencies": {"yargs": "18.0.0"}}
    out = patch_package_json_for_candidate(pkg, "yargs", "18.2.0")
    assert out["devDependencies"]["yargs"] == "18.2.0"
    assert "overrides" not in out


def test_nested_transitive_edge_still_checks_root_direct_dependency():
    # the specific bug: the EDGE under test can be nested (e.g. from a
    # workspace member), but if the root package.json separately declares
    # the same package name as a direct dependency, that root declaration
    # must still be patched -- overrides alone would EOVERRIDE-conflict
    # with it. This function only ever sees the root package.json, so this
    # test just confirms detection doesn't depend on any parent_path input.
    pkg = {"name": "root", "devDependencies": {"yargs": "18.0.0"}}
    out = patch_package_json_for_candidate(pkg, "yargs", "18.2.0")
    assert out["devDependencies"]["yargs"] == "18.2.0"


def test_transitive_only_package_uses_overrides():
    # a package name that is NOT anywhere in the root's own dependency
    # fields should fall back to `overrides`, which is the correct
    # mechanism for purely transitive packages.
    pkg = {"name": "root", "dependencies": {"express": "^4.0.0"}}
    out = patch_package_json_for_candidate(pkg, "some-transitive-dep", "2.0.0")
    assert out["overrides"] == {"some-transitive-dep": "2.0.0"}
    assert "some-transitive-dep" not in out["dependencies"]


def test_existing_overrides_for_other_packages_are_preserved():
    pkg = {"name": "root", "dependencies": {"express": "^4.0.0"},
           "overrides": {"@babel/core": "$@babel/core"}}
    out = patch_package_json_for_candidate(pkg, "some-transitive-dep", "2.0.0")
    assert out["overrides"]["@babel/core"] == "$@babel/core"
    assert out["overrides"]["some-transitive-dep"] == "2.0.0"


def test_input_dict_is_never_mutated():
    # patch_package_json_for_candidate is called against a shared
    # PackageJsonCache entry reused across every candidate for a repo --
    # mutating the input would leak one candidate's override into the next.
    pkg = {"name": "root", "dependencies": {"yargs": "18.0.0"}}
    original_deps_id = id(pkg["dependencies"])
    patch_package_json_for_candidate(pkg, "yargs", "18.2.0")
    assert pkg["dependencies"]["yargs"] == "18.0.0"  # untouched
    assert id(pkg["dependencies"]) == original_deps_id


def test_field_priority_is_first_match_dependencies_before_dev():
    # if (unusually) the same name appeared in both dependencies and
    # devDependencies, only one field should be patched -- deterministic,
    # not both, to avoid ambiguity about which range npm should honor.
    pkg = {"name": "root", "dependencies": {"yargs": "^18.0.0"},
           "devDependencies": {"yargs": "^17.0.0"}}
    out = patch_package_json_for_candidate(pkg, "yargs", "18.2.0")
    patched_fields = [f for f in ("dependencies", "devDependencies") if out[f].get("yargs") == "18.2.0"]
    assert len(patched_fields) == 1
