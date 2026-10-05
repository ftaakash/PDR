"""Pre-specified Layer 3 report (docs/phase3_protocol.md S10) on SYNTHETIC records only."""
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from test_phase3_logic import AUDIT_OK, arm, b0_arm, pdr_arm, rec, st  # noqa: E402

from pdr import phase3 as p3  # noqa: E402


def _mod():
    path = os.path.join(os.path.dirname(__file__), "..", "scripts", "phase3_report.py")
    spec = importlib.util.spec_from_file_location("phase3_report", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


AUDIT_WORSE = AUDIT_OK + "1 package has missing registry signatures\n"
AUDIT_MORE_ATT = ("audited 10 packages in 2s\n\n10 packages have verified registry signatures\n\n"
                  "4 packages have verified attestations\n")


def fixture():
    return [
        rec("a", pdr=pdr_arm(audit_text=AUDIT_MORE_ATT)),                 # OK, attestation gain +1
        rec("a", pdr=pdr_arm(test_runs=(1,))),                            # TEST_FAIL (attributable)
        rec("b", pdr=pdr_arm(tree={"a": "1", "b": "1"})),                 # NO_BEHAVIORAL_CHANGE
        rec("c", pdr=pdr_arm(install=st(1), test={"ran": False})),       # INSTALL_FAIL (arm stops)
        rec("d", b0=arm(test_runs=(0, 1))),                               # OK but flaky B0
        rec("e", pdr=pdr_arm(audit_text=AUDIT_WORSE)),                    # AUDIT_SIGNATURE_CHANGE
    ]


def test_outcomes_are_recomputed_not_trusted():
    rs = fixture()
    rs[0]["classification"] = {"outcome": "TEST_FAIL"}   # stale stored verdict must be ignored
    out = _mod().build(rs)
    assert out["n_valid"] == 6 and out["invalid_records"] == []
    assert out["outcome_counts"] == {"OK": 2, "TEST_FAIL": 1, "NO_BEHAVIORAL_CHANGE": 1,
                                     "INSTALL_FAIL": 1, "AUDIT_SIGNATURE_CHANGE": 1}


def test_invalid_records_are_listed_and_excluded():
    rs = fixture() + [{"repo": "z", "edge_id": "z#1"}]
    out = _mod().build(rs)
    assert out["n_records"] == 7 and out["n_valid"] == 6
    assert out["invalid_records"][0]["edge_id"] == "z#1"


def test_primary_is_test_delta_excluding_flaky_and_marked_underpowered():
    out = _mod().build(fixture())
    pr = out["primary"]
    assert pr["stage"] == "test"
    # c never reaches tests (install fails) and d is flaky-B0 -> 4 pairs, 1 new failure
    assert pr["n_pairs"] == 4 and pr["new_failures_b"] == 1 and pr["fixes_c"] == 0
    assert pr["underpowered"] and out["flags"]["NO_GATE_D_CLAIM"]


def test_audit_summary_and_attestation_gain():
    out = _mod().build(fixture())
    a = out["audit"]
    assert a["audit_signature_change"] == 1 and a["missing_delta_sum"] == 1 and a["pairs_parse_failed"] == 0
    g = out["attestation_gain"]
    assert g["gain_gt0"] == 1 and g["gain_lt0"] == 0


def test_audit_is_never_a_paired_delta():
    assert p3.paired_delta(fixture(), "audit")["n_pairs"] == 0
    assert "audit" not in _mod().build(fixture())["paired_deltas"]


def test_viability_both_estimands_and_usable_baseline():
    v = _mod().build(fixture())["viability_ok_rate"]
    assert v["all_valid"]["successes"] == 2 and v["all_valid"]["n"] == 6
    assert v["all_valid"]["repo_weighted_pct"] == 30.0      # repo means a .5, b 0, c 0, d 1, e 0
    assert v["usable_baseline"]["n"] == 5                   # d excluded (flaky B0)


def test_flags():
    f = _mod().build(fixture())["flags"]
    assert f["b0_invalid"] == 1 and not f["REWORK"]
    # completed (no failure stage): OK a, NBC b, OK d -> NBC share 1/3
    assert abs(f["no_behavioral_change_share_of_completed"] - 1 / 3) < 1e-9 and not f["LAYER3_ADDS_NOTHING"]
    many_broken = [rec(r, b0=arm(test_runs=(1, 1))) for r in "abcd"]
    assert _mod().build(many_broken)["flags"]["REWORK"]


def test_empty_input():
    out = _mod().build([])
    assert out["n_valid"] == 0 and out["viability_ok_rate"]["all_valid"] is None
    assert out["flags"]["NO_GATE_D_CLAIM"] and not out["flags"]["REWORK"]
