"""
pdr.policy
===========
Implements the FROZEN definitions from the operational ladder (README.md /
PDR_Proposal_and_Implementation_Plan.md) as executable classification logic.

BOUNDARY THAT MUST NEVER BE CROSSED (Kill Test 13 / integrity+scope boundary
in README): provenance = origin/integrity evidence, NOT a safety judgment.
Nothing in this module, its outputs, or its field names may assert or imply
"recoverable" or "provenanced" == "safe". `tests/test_no_safety_claims.py`
enforces this mechanically against this module's public vocabulary and
against the memo template.

STATES (5 + unknown -- this is the classification `tests/` checks against):
    PROVENANCED
        Resolved version already has provenance. Not deficient. Not "safe" --
        merely "has origin evidence at the currently resolved version".
    DEFICIENT_UNRECOVERABLE
        OPG=true. No provenance-bearing version exists anywhere in the
        package's declared semver range. Nothing to recover.
    DEFICIENT_SEMANTIC_ONLY
        OPG=true. A provenance-bearing version exists within the declared
        range (semantic recovery), but the best such candidate falls outside
        the resolution-preserving tolerance band (see RESOLUTION_TOLERANCE
        below) relative to the version actually resolved.
    DEFICIENT_RESOLUTION_PRESERVING
        OPG=true. Semantic recovery exists AND the best candidate is within
        the resolution-preserving tolerance band. NOTE: this is as far as
        this pilot pipeline evaluates. Deployability (peer/audit/test
        survival) and incremental enforcement cost are NOT evaluated here --
        see docs/gate_status.md. A DEFICIENT_RESOLUTION_PRESERVING edge is
        NOT a claim that the recovery is deployable.
    UNKNOWN
        Provenance status of the resolved version, or of the range scan,
        could not be determined: unresolved edge (missing/link/git/file
        target), registry packument fetch failed, or malformed version
        string. Counted separately from DEFICIENT_* -- an unknown is not
        evidence of deficiency, and (Gate criterion F) must stay <=20% of
        edges for the pilot's OPG/PD estimates to be trusted at all.

RESOLUTION-PRESERVING TOLERANCE (the specific operationalization Kill Test 3
in the audit prompt is aimed squarely at -- flagged, not hidden):
    We anchor tolerance to the RESOLVED version, not the declared range,
    because "semantic recovery" already guarantees range membership by
    definition -- so measuring resolution-preserving recovery against the
    range would collapse the two constructs into one. Instead:
        resolution_preserving := semver.diff(resolved, candidate) in
                                  {None, "patch", "minor"}
    i.e. the candidate may differ from what's actually resolved today by at
    most a minor-or-patch step (in either direction), never a major step,
    regardless of how wide the declared range technically is. This is a
    conservative, declared, v0.1 proxy for "doesn't change version intent
    beyond a predefined tolerance" -- it does NOT simulate full-tree
    re-resolution (dedup/hoisting effects on OTHER edges that depend on the
    same package), which is the harder, truer version of this construct and
    is left to Phase 2 (see docs/gate_status.md, Kill Test 3).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from pdr.provenance import Packument
from pdr.resolve import Edge
from pdr.semver_client import run_batch

RESOLUTION_TOLERANCE = {None, "patch", "minor"}

STATE_PROVENANCED = "PROVENANCED"
STATE_UNRECOVERABLE = "DEFICIENT_UNRECOVERABLE"
STATE_SEMANTIC_ONLY = "DEFICIENT_SEMANTIC_ONLY"
STATE_RESOLUTION_PRESERVING = "DEFICIENT_RESOLUTION_PRESERVING"
STATE_UNKNOWN = "UNKNOWN"

ALL_STATES = [
    STATE_PROVENANCED,
    STATE_UNRECOVERABLE,
    STATE_SEMANTIC_ONLY,
    STATE_RESOLUTION_PRESERVING,
    STATE_UNKNOWN,
]


@dataclass
class Classification:
    edge: Edge
    state: str
    candidate_version: Optional[str] = None
    reason: str = ""
    resolved_time: Optional[str] = None  # publish timestamp of the RESOLVED version, for era stratification (Gate A)


def _valid_range_task(range_str: str) -> Dict:
    return {"op": "validRange", "range": range_str}


def classify_edges(edges: List[Edge], packuments: Dict[str, Packument]) -> List[Classification]:
    """Performance note: this batches every semver question across the WHOLE
    edge list into a small, fixed number of subprocess calls to
    scripts/semver_helper.js, rather than one call per edge. An earlier
    per-edge-call version worked fine on the 7-repo pilot (~19k edges) but
    stalled on a 45-repo run (~70k edges, ~58k deficient) because subprocess
    *spawn* overhead, not the semver computation itself, dominated: 3 spawns
    per deficient edge is >170k Node process launches. Below, work is deduped
    by the (dep_name, declared_range) key -- many edges across different
    repos/parents ask the exact same semver question -- and every remaining
    per-key/per-edge task is flushed in a handful of single large batches.
    """
    out: List[Classification] = []

    # ---- Pass 1: split out edges we can't even ask the question for ----
    usable = []
    for e in edges:
        if e.resolved_kind != "registry" or e.resolved_version is None:
            out.append(Classification(e, STATE_UNKNOWN, reason=f"resolved_kind={e.resolved_kind}"))
            continue
        pk = packuments.get(e.dep_name)
        if pk is None or not pk.found:
            out.append(Classification(e, STATE_UNKNOWN, reason="packument_not_found"))
            continue
        vfacts = pk.versions.get(e.resolved_version)
        if vfacts is None:
            out.append(Classification(e, STATE_UNKNOWN, reason="resolved_version_missing_from_packument"))
            continue
        usable.append((e, pk, vfacts))

    # ---- Pass 2: split provenanced vs deficient ----
    deficient = []
    for e, pk, vfacts in usable:
        if vfacts.has_provenance:
            out.append(Classification(e, STATE_PROVENANCED, resolved_time=vfacts.time))
        else:
            deficient.append((e, pk, vfacts))

    if not deficient:
        return out

    # ---- Pass 3a: validRange, deduped across the whole dataset, ONE call ----
    unique_ranges = sorted({e.declared_range for e, _, _ in deficient})
    range_validity: Dict[str, bool] = {}
    for r, res in zip(unique_ranges, run_batch([_valid_range_task(r) for r in unique_ranges])):
        range_validity[r] = bool(res.get("ok") and res.get("result"))

    # ---- Pass 3b: build (dep_name, range) keys for edges with a valid range ----
    # key -> provenanced versions in range (filled in 3c)
    keyed: Dict[tuple, dict] = {}
    for e, pk, vfacts in deficient:
        if not range_validity.get(e.declared_range, False):
            out.append(Classification(e, STATE_UNKNOWN, reason=f"unparseable_range:{e.declared_range}",
                                       resolved_time=vfacts.time))
            continue
        key = (e.dep_name, e.declared_range)
        if key not in keyed:
            provenanced_versions = [v for v, vf in pk.versions.items() if vf.has_provenance]
            keyed[key] = {"pk": pk, "provenanced_versions": provenanced_versions, "edges": []}
        keyed[key]["edges"].append((e, vfacts))

    if not keyed:
        return out

    # ---- Pass 3c: satisfies -- ONE call covering every (key, candidate-version) pair ----
    sat_tasks = []
    sat_index = []  # parallel list of (key, version)
    for key, info in keyed.items():
        for v in info["provenanced_versions"]:
            sat_tasks.append({"op": "satisfies", "version": v, "range": key[1]})
            sat_index.append((key, v))
    sat_results = run_batch(sat_tasks) if sat_tasks else []
    for (key, v), res in zip(sat_index, sat_results):
        if res.get("ok") and res.get("result"):
            keyed[key].setdefault("satisfying", []).append(v)

    # ---- Pass 3d: maxSatisfying -- ONE call, one task per key that has candidates ----
    max_keys = [k for k, info in keyed.items() if info.get("satisfying")]
    max_tasks = [{"op": "maxSatisfying", "versions": keyed[k]["satisfying"], "range": k[1]} for k in max_keys]
    max_results = run_batch(max_tasks) if max_tasks else []
    for k, res in zip(max_keys, max_results):
        keyed[k]["candidate"] = res.get("result") if res.get("ok") else sorted(keyed[k]["satisfying"])[-1]

    # ---- Pass 3e: diff -- ONE call, one task per edge that has a candidate ----
    diff_tasks = []
    diff_index = []  # parallel list of (key, edge, vfacts)
    for key, info in keyed.items():
        candidate = info.get("candidate")
        if candidate is None:
            continue
        for e, vfacts in info["edges"]:
            diff_tasks.append({"op": "diff", "a": e.resolved_version, "b": candidate})
            diff_index.append((key, e, vfacts))
    diff_results = run_batch(diff_tasks) if diff_tasks else []

    diffed_edge_ids = set()
    for (key, e, vfacts), res in zip(diff_index, diff_results):
        candidate = keyed[key]["candidate"]
        diffed_edge_ids.add(id(e))
        if not res.get("ok"):
            out.append(Classification(e, STATE_UNKNOWN, reason="diff_failed", resolved_time=vfacts.time))
            continue
        diff = res.get("result")
        if diff in RESOLUTION_TOLERANCE:
            out.append(Classification(e, STATE_RESOLUTION_PRESERVING, candidate_version=candidate,
                                       reason=f"diff={diff}", resolved_time=vfacts.time))
        else:
            out.append(Classification(e, STATE_SEMANTIC_ONLY, candidate_version=candidate,
                                       reason=f"diff={diff}_exceeds_tolerance", resolved_time=vfacts.time))

    # ---- Pass 3f: everything left in `keyed` with no satisfying/candidate version at all ----
    for key, info in keyed.items():
        candidate = info.get("candidate")
        for e, vfacts in info["edges"]:
            if candidate is not None and id(e) in diffed_edge_ids:
                continue
            reason = "no_provenanced_version_exists_at_all" if not info["provenanced_versions"] else (
                "no_in_range_provenanced_version" if not info.get("satisfying") else "maxSatisfying_returned_none")
            out.append(Classification(e, STATE_UNRECOVERABLE, reason=reason, resolved_time=vfacts.time))

    return out
