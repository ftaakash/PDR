"""
pdr.layer1_alt
===============
Pure decision logic for experiment `layer1_alt_v1` (docs/phase2_protocol.md
Section 7): which lower provenance-bearing versions an edge may retry, how a
failed npm resolution is classified, and how an edge's attempt sequence is
summarised. Execution lives in scripts/layer1_alt_resolution.py; npm-semver
questions are answered by scripts/semver_helper.js and passed in, so nothing
here re-implements npm's range grammar.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from pdr.sandbox import OK, PEER_CONFLICT, RESOLUTION_FAIL

EXPERIMENT_ID = "layer1_alt_v1"
K_MAX = 5
T_CUT = "2026-09-24T00:00:00Z"
RESOLUTION_TOLERANCE = {None, "patch", "minor"}   # must equal pdr.policy.RESOLUTION_TOLERANCE

NO_ALTERNATIVE = "NO_ALTERNATIVE"
ALT_OK = "ALT_OK"
ALT_EXHAUSTED = "ALT_EXHAUSTED"     # every tried alternative failed
DRIFT_OK = "DRIFT_OK"              # original candidate now resolves OK; not credited


def _published_by(time: Optional[str], t_cut: str) -> bool:
    # ISO-8601 UTC strings from the registry compare correctly as text once
    # normalised to the same precision; a missing time cannot be shown to
    # predate the cut-off, so it is excluded.
    if not time:
        return False
    return time[:19] <= t_cut[:19]


def alternative_candidates(ordered_desc: Iterable[str], facts: Dict[str, dict],
                           t_cut: str = T_CUT, k: int = K_MAX) -> dict:
    """Return the retry list for one edge.

    ordered_desc: the package's versions in descending semver order (from
        semver.rsort).
    facts: version -> {"has_provenance": bool, "time": str|None,
        "satisfies": bool (declared range, includePrerelease false),
        "diff": semver.diff(resolved, v), "lt_original": bool}.
    Returns {"alternatives": [...<=k], "n_qualifying": int,
             "n_excluded_by_t_cut": int}.
    """
    qualifying, excluded_by_time = [], 0
    for v in ordered_desc:
        f = facts.get(v)
        if not f:
            continue
        if not (f["has_provenance"] and f["satisfies"] and f["lt_original"]
                and f["diff"] in RESOLUTION_TOLERANCE):
            continue
        if not _published_by(f.get("time"), t_cut):
            excluded_by_time += 1
            continue
        qualifying.append(v)
    return {"alternatives": qualifying[:k], "n_qualifying": len(qualifying),
            "n_excluded_by_t_cut": excluded_by_time}


def classify_npm_failure(stderr: str) -> str:
    """Non-zero `npm install --package-lock-only` exit: ERESOLVE is a peer
    conflict (the rule Layer 1's documented reclassification applied), anything
    else is a resolution failure."""
    return PEER_CONFLICT if "ERESOLVE" in (stderr or "") else RESOLUTION_FAIL


def summarise_edge(alternatives: List[str], outcomes: Dict[str, str],
                   attempt0_outcome: Optional[str]) -> dict:
    """Walk an edge's alternatives in order, stopping at the first OK.
    `outcomes` maps version -> outcome for this (repo, package). Returns
    `alt_status` (NO_ALTERNATIVE / ALT_OK / ALT_EXHAUSTED, from the
    alternatives alone), `drift` (attempt 0 now OK), `credited` (counts toward
    the exists-any estimand: ALT_OK and not drift), the 1-based index of the
    first OK alternative, and the attempts consumed. Raises KeyError if an
    attempt the walk needs is missing, so an incomplete run cannot be
    summarised by accident."""
    drift = attempt0_outcome == OK
    tried: List[str] = []
    alt_status, first_ok = (NO_ALTERNATIVE if not alternatives else ALT_EXHAUSTED), None
    for i, v in enumerate(alternatives, 1):
        o = outcomes[v]
        tried.append(o)
        if o == OK:
            alt_status, first_ok = ALT_OK, i
            break
    return {"alt_status": alt_status, "drift": drift, "credited": alt_status == ALT_OK and not drift,
            "status": DRIFT_OK if drift else alt_status,
            "first_ok_index": first_ok, "attempts_used": len(tried), "alt_outcomes": tried}
