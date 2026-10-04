"""
tests/test_no_safety_claims.py
Kill Test 13 / README "Integrity + scope boundary": provenance = origin,
NOT safety. This is enforced mechanically, not just by convention: scan the
source of pdr/policy.py (where the state vocabulary lives) and the rendered
kill_memo.md template for phrases that would equate a state name with
"safe"/"safety"/"secure". A future edit that tries to shortcut this (e.g.
renaming DEFICIENT_RESOLUTION_PRESERVING's docstring to say "-> safe to
adopt") should fail this test.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pdr.policy as policy  # noqa: E402
import scripts.analyze_kill as analyze_kill  # noqa: E402

FORBIDDEN_PATTERNS = [
    r"provenanced\s*=+\s*safe",
    r"recoverable\s*=+\s*safe",
    r"deployable\s*=+\s*safe",
    r"is\s+safe\s+to\s+(adopt|install|use)",
    r"guarantees?\s+(safety|security)",
]


def _scan(text: str, source_label: str):
    lowered = text.lower()
    for pat in FORBIDDEN_PATTERNS:
        m = re.search(pat, lowered)
        assert m is None, f"forbidden safety-equivalence phrase in {source_label}: {m.group(0)!r}"


def test_policy_module_source_has_no_safety_equivalence():
    with open(policy.__file__, "r", encoding="utf-8") as f:
        _scan(f.read(), "pdr/policy.py")


def test_policy_module_asserts_the_boundary_explicitly():
    with open(policy.__file__, "r", encoding="utf-8") as f:
        text = f.read().lower()
    assert "not a safety judgment" in text or "not a safety" in text, (
        "pdr/policy.py should explicitly state the provenance != safety "
        "boundary somewhere in its docstring"
    )


def test_memo_template_has_no_safety_equivalence_and_states_boundary():
    fake_summary = {
        "pilot_disclaimer": "x",
        "overall": {
            "opg_pct_of_known": 10.0,
            "semantic_recovery_pct_of_deficient": 5.0,
            "resolution_preserving_pct_of_deficient": 4.0,
        },
        "gate": {k: {"verdict": "PASS"} for k in [
            "A_opg_era_controlled", "B_semantic_pd", "C_semantic_to_operational_gap",
            "D_excess_enforcement_cost", "E_robustness", "F_unknowns_bounded",
        ]},
        "overall_verdict_measured_criteria_only": "PARTIAL_GO_PENDING_C_D",
    }
    tmp_path = "/tmp/_pdr_test_memo.md"
    analyze_kill._write_memo(fake_summary, tmp_path)
    with open(tmp_path, "r", encoding="utf-8") as f:
        rendered = f.read()
    _scan(rendered, "kill_memo.md template render")
    assert "a safety claim" in rendered.lower()
