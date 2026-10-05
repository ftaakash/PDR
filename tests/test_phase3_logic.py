"""
tests/test_phase3_logic.py
Unit tests for pdr.phase3 using SYNTHETIC arm records. Nothing here is Layer 3
data: real results only ever come from isolated_worker/. These tests pin the
meaning of every outcome BEFORE any real result exists, so the interpretation
cannot drift toward whatever the first real numbers happen to look like.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pdr import phase3 as p3  # noqa: E402
from pdr import sandbox as sb  # noqa: E402

AUDIT_OK = ("audited 10 packages in 2s\n\n10 packages have verified registry signatures\n\n"
            "3 packages have verified attestations\n")


def st(exit_code=0, **kw):
    d = {"ran": True, "exit_code": exit_code, "elapsed_s": 1.0, "timed_out": False, "oom": False,
         "stdout_tail": "", "stderr_tail": ""}
    d.update(kw)
    return d


def arm(tree=None, test_runs=(0,), audit_text=AUDIT_OK, peer=(), **overrides):
    stages = {
        "install": st(0),
        "lifecycle": st(0),
        "peer": st(0, problems=list(peer)),
        "audit": st(0, stdout_tail=audit_text),
        "test": {"ran": True, "runs": [{"exit_code": c, "timed_out": False, "oom": False} for c in test_runs]},
    }
    stages.update(overrides)
    return {"stages": stages, "tree_versions": tree if tree is not None else {"a": "1", "b": "1"}}


def pdr_arm(tree=None, **kw):
    a = arm(tree=tree if tree is not None else {"a": "1", "b": "2"}, **kw)
    a["stages"]["resolve"] = st(0)
    return a


def b0_arm(**kw):
    return arm(test_runs=(0, 0), **kw)


def rec(repo="r1", b0=None, pdr=None):
    return {"schema_version": p3.SCHEMA_VERSION, "edge_id": f"{repo}#1", "repo": repo, "dep_name": "b",
            "resolved_version": "1", "candidate_version": "2", "size_bucket": "medium",
            "patch_mode": "overrides", "pinned_sha": "abc", "image_id": "sha256:x",
            "b0": b0 or b0_arm(), "pdr": pdr or pdr_arm()}


def test_taxonomy_contains_every_reviewer_named_outcome():
    for name in ["LIFECYCLE_FAIL", "TEST_FAIL", "NO_BEHAVIORAL_CHANGE", "TIMEOUT", "RESOURCE_LIMIT",
                 "AUDIT_SIGNATURE_CHANGE", "PEER_CONFLICT", "OK"]:
        assert name in p3.OUTCOMES


def test_clean_run_is_ok():
    c = p3.classify_pair(b0_arm(), pdr_arm())
    assert c["outcome"] == sb.OK and c["failure_stage"] is None and c["tree_diff_size"] == 1


def test_identical_tree_is_no_behavioral_change_not_ok():
    c = p3.classify_pair(b0_arm(tree={"a": "1"}), pdr_arm(tree={"a": "1"}))
    assert c["outcome"] == sb.NO_BEHAVIORAL_CHANGE


def test_install_failure_attributable_only_if_b0_installed():
    bad = pdr_arm(install=st(1, stderr_tail="boom"))
    c = p3.classify_pair(b0_arm(), bad)
    assert c["outcome"] == sb.INSTALL_FAIL and c["failure_stage"] == "install" and c["attributable"]["install"]
    c2 = p3.classify_pair(b0_arm(install=st(1)), bad)
    assert c2["outcome"] == sb.INSTALL_FAIL and not c2["attributable"]["install"]


def test_eresolve_is_peer_conflict_not_generic_failure():
    bad = pdr_arm(install=st(1, stderr_tail="npm error code ERESOLVE"))
    assert p3.classify_pair(b0_arm(), bad)["outcome"] == sb.PEER_CONFLICT


def test_lifecycle_failure_is_distinct_from_install_failure():
    c = p3.classify_pair(b0_arm(), pdr_arm(lifecycle=st(1)))
    assert c["outcome"] == sb.LIFECYCLE_FAIL and c["failure_stage"] == "lifecycle"


def test_only_new_peer_problems_count():
    same = p3.classify_pair(b0_arm(peer=["invalid: x"]), pdr_arm(peer=["invalid: x"]))
    assert same["outcome"] == sb.OK
    new = p3.classify_pair(b0_arm(peer=["invalid: x"]), pdr_arm(peer=["invalid: x", "peer dep missing: y"]))
    assert new["outcome"] == sb.PEER_CONFLICT and new["failure_stage"] == "peer"


def test_audit_regression_detected_and_attestation_gain_reported():
    worse = "10 packages have verified registry signatures\n1 packages have invalid registry signatures\n"
    c = p3.classify_pair(b0_arm(), pdr_arm(audit_text=worse))
    assert c["outcome"] == p3.AUDIT_SIGNATURE_CHANGE
    better = AUDIT_OK.replace("3 packages have verified attestations", "5 packages have verified attestations")
    c2 = p3.classify_pair(b0_arm(), pdr_arm(audit_text=better))
    assert c2["outcome"] == sb.OK and c2["attestation_gain"] == 2


def test_unparseable_audit_is_surfaced_not_silently_passed():
    c = p3.classify_pair(b0_arm(), pdr_arm(audit_text="npm error Failed to download"))
    assert c["audit_parse_ok"] is False and c["attestation_gain"] is None
    assert c["outcome"] == sb.OK  # no evidence of change -- but flagged False, never True


def test_test_failure_attributable_only_when_b0_reliably_passes():
    pdr_bad = pdr_arm(test_runs=(1,))
    c = p3.classify_pair(b0_arm(), pdr_bad)
    assert c["outcome"] == sb.TEST_FAIL and c["attributable"]["test"] and c["b0_test_status"] == "PASS"
    flaky = arm(test_runs=(0, 1))
    c2 = p3.classify_pair(flaky, pdr_bad)
    assert c2["b0_test_status"] == "FLAKY" and not c2["attributable"]["test"]
    failing = arm(test_runs=(1, 1))
    assert not p3.classify_pair(failing, pdr_bad)["attributable"]["test"]


def test_timeout_and_oom_map_to_their_own_outcomes():
    t = pdr_arm(install=st(None, timed_out=True))
    assert p3.classify_pair(b0_arm(), t)["outcome"] == sb.TIMEOUT
    o = pdr_arm(install=st(137, oom=True))
    assert p3.classify_pair(b0_arm(), o)["outcome"] == sb.RESOURCE_LIMIT
    tt = pdr_arm(); tt["stages"]["test"]["runs"][0]["timed_out"] = True
    assert p3.classify_pair(b0_arm(), tt)["outcome"] == sb.TIMEOUT


def test_first_failure_wins_when_multiple_stages_fail():
    both = pdr_arm(lifecycle=st(1), test_runs=(1,))
    c = p3.classify_pair(b0_arm(), both)
    assert c["failure_stage"] == "lifecycle"


def test_paired_delta_counts_new_failures_and_fixes_and_excludes_flaky():
    rs = [rec("a", pdr=pdr_arm(test_runs=(1,))),          # new failure
          rec("b", pdr=pdr_arm(test_runs=(0,))),          # clean
          rec("c", b0=arm(test_runs=(1, 1)), pdr=pdr_arm(test_runs=(0,))),   # fix
          rec("d", b0=arm(test_runs=(0, 1)), pdr=pdr_arm(test_runs=(1,)))]   # flaky -> excluded
    d = p3.paired_delta(rs, "test", n_boot=200)
    assert d["n_pairs"] == 3 and d["new_failures_b"] == 1 and d["fixes_c"] == 1 and d["delta"] == 0.0


def test_paired_delta_ci_requires_multiple_repos():
    one = [rec("a", pdr=pdr_arm(test_runs=(1,))), rec("a")]
    assert p3.paired_delta(one, "test", n_boot=50)["ci95"] is None
    many = [rec("a", pdr=pdr_arm(test_runs=(1,))), rec("b"), rec("c")]
    ci = p3.paired_delta(many, "test", n_boot=200)["ci95"]
    assert ci is not None and ci[0] <= ci[1]


def test_paired_delta_is_seed_reproducible():
    rs = [rec("a", pdr=pdr_arm(test_runs=(1,))), rec("b"), rec("c"), rec("d", pdr=pdr_arm(test_runs=(1,)))]
    assert p3.paired_delta(rs, "test", n_boot=300, seed=1) == p3.paired_delta(rs, "test", n_boot=300, seed=1)


def test_funnel_is_monotone_and_attribution_aware():
    rs = [rec("a"), rec("b", pdr=pdr_arm(install=st(1))),
          rec("c", pdr=pdr_arm(test_runs=(1,))), rec("d", b0=arm(install=st(1)), pdr=pdr_arm(install=st(1)))]
    rows = p3.funnel(rs)
    entering = [r["entering"] for r in rows]
    assert entering == sorted(entering, reverse=True)
    install = next(r for r in rows if r["stage"] == "install")
    assert install["attributable"] == 3 and install["failed"] == 1   # 'd' excluded: B0 also fails
    assert p3.funnel([]) [0]["pass_rate"] is None


def test_validate_record_flags_missing_and_unknown():
    assert p3.validate_record(rec()) == []
    bad = rec(); del bad["pinned_sha"]; bad["pdr"]["stages"]["bogus"] = {}
    probs = p3.validate_record(bad)
    assert any("pinned_sha" in x for x in probs) and any("bogus" in x for x in probs)


def test_parse_audit_signatures_variants():
    assert p3.parse_audit_signatures(AUDIT_OK)["verified_attestations"] == 3
    assert p3.parse_audit_signatures("1 package has verified attestations")["verified_attestations"] == 1
    assert p3.parse_audit_signatures("")["parse_ok"] is False
    assert p3.parse_audit_signatures("npm error Failed to download")["parse_ok"] is False


def test_pdr_runs_twice_and_flaky_pdr_is_its_own_outcome():
    # T7 amendment 2026-10-05: PDR tests run twice; disagreement is TEST_FLAKY, not TEST_FAIL
    flaky_pdr = pdr_arm(test_runs=(0, 1))
    c = p3.classify_pair(b0_arm(), flaky_pdr)
    assert c["outcome"] == p3.TEST_FLAKY and c["pdr_test_status"] == "FLAKY" and not c["attributable"]["test"]
    both_fail = pdr_arm(test_runs=(1, 1))
    c2 = p3.classify_pair(b0_arm(), both_fail)
    assert c2["outcome"] == sb.TEST_FAIL and c2["attributable"]["test"]
    both_pass = pdr_arm(test_runs=(0, 0))
    assert p3.classify_pair(b0_arm(), both_pass)["outcome"] == sb.OK


def test_paired_test_delta_excludes_flaky_pdr():
    rs = [rec("a", pdr=pdr_arm(test_runs=(0, 1))), rec("b", pdr=pdr_arm(test_runs=(1, 1))), rec("c")]
    d = p3.paired_delta(rs, "test", n_boot=100)
    assert d["n_pairs"] == 2 and d["new_failures_b"] == 1


def test_orchestrator_runs_pdr_tests_twice():
    import importlib.util
    path = os.path.join(os.path.dirname(__file__), "..", "isolated_worker", "orchestrate.py")
    spec = importlib.util.spec_from_file_location("orch", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.CFG["pdr_test_runs"] == 2 and m.CFG["b0_test_runs"] == 2


def test_empty_worker_result_is_worker_error_never_ok():
    # regression: the first real --limit 2 run (2026-10-05) produced arms with no stages
    # ("no result line") and classify_pair called them OK
    empty = {"arm": "b0", "stages": {}, "tree_versions": {}, "orchestrator_note": "no result line"}
    for b0, pdr in [(empty, dict(empty, arm="pdr")), (b0_arm(), dict(empty, arm="pdr")), (empty, pdr_arm())]:
        c = p3.classify_pair(b0, pdr)
        assert c["outcome"] == p3.WORKER_ERROR and not any(c["attributable"].values())
    r = rec("a", b0=empty, pdr=dict(empty, arm="pdr"))
    assert any("worker produced no result" in x for x in p3.validate_record(r))
    rows = p3.funnel([r])
    assert all(row["attributable"] == 0 for row in rows)
