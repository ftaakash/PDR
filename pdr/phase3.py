"""
pdr.phase3
===========
Layer 3 (behavioral validation) result schema and analysis logic. PURE LOGIC
ONLY: nothing in this module runs npm, spawns a process, or touches the
network. Execution lives exclusively in isolated_worker/ (which runs inside a
disposable container -- docs/phase3_protocol.md Section 2). This split is
deliberate: everything that decides what a result MEANS can be unit-tested
here, on any machine, with synthetic inputs.

Design decisions frozen in docs/phase3_protocol.md (read that first):

* Arms. B0 = original repo, no substitution. PDR = repo with the Layer-1
  confirmed substitution. B1 (existing checker baseline) is NOT a third
  install: it is `npm audit signatures` run on the B0 tree, matching
  docs/methodology_freeze.md Section 8. Delta-audit therefore compares the
  audit result of the PDR tree against the audit result of the B0 tree.
* Pairing. Every PDR run is paired with the B0 run for the same repo. Whether
  a PDR failure is ATTRIBUTABLE to the substitution depends on whether B0
  passed the same stage; a failure that B0 also has is recorded but never
  counted toward a delta (it says nothing about PDR).
* Stage order: resolve -> install -> lifecycle -> peer -> audit -> test.
* First-failure semantics: `outcome` names the FIRST failing stage in that
  order; later stages are still recorded where the run continued.

Outcome vocabulary extends pdr.sandbox's (which reserved the Layer-3 names).
NO_BEHAVIORAL_CHANGE is given a concrete definition here for the first time:
the substitution produced an installed tree identical to B0's, i.e. nothing
was actually tested.
"""
from __future__ import annotations

import random
import re
from typing import Dict, List, Optional, Tuple

from pdr import sandbox as sb

SCHEMA_VERSION = "phase3.v1"

STAGES = ["resolve", "install", "lifecycle", "peer", "audit", "test"]

# Outcomes (superset of pdr.sandbox.ALL_OUTCOMES, plus AUDIT_SIGNATURE_CHANGE)
AUDIT_SIGNATURE_CHANGE = "AUDIT_SIGNATURE_CHANGE"
# T7 amendment 2026-10-05 (docs/phase3_protocol.md Section 3.1): PDR tests run
# twice like B0's. If the two PDR runs disagree, the substitution's test effect
# is undetermined -- recorded as TEST_FLAKY, never as TEST_FAIL or OK.
TEST_FLAKY = "TEST_FLAKY"
OUTCOMES = [
    sb.OK, sb.RESOLUTION_FAIL, sb.INSTALL_FAIL, sb.LIFECYCLE_FAIL, sb.PEER_CONFLICT,
    AUDIT_SIGNATURE_CHANGE, sb.TEST_FAIL, TEST_FLAKY, sb.NO_BEHAVIORAL_CHANGE, sb.TIMEOUT, sb.RESOURCE_LIMIT,
]

# stage -> outcome name when that stage fails for a reason other than timeout/OOM
_STAGE_FAIL_OUTCOME = {
    "resolve": sb.RESOLUTION_FAIL,
    "install": sb.INSTALL_FAIL,
    "lifecycle": sb.LIFECYCLE_FAIL,
    "peer": sb.PEER_CONFLICT,
    "audit": AUDIT_SIGNATURE_CHANGE,
    "test": sb.TEST_FAIL,
}


# ---------------------------------------------------------------- stage helpers

def stage_ran(arm: dict, stage: str) -> bool:
    s = (arm.get("stages") or {}).get(stage)
    return bool(s and s.get("ran"))


def stage_kind(arm: dict, stage: str) -> Optional[str]:
    """None if the stage did not run or passed; else 'TIMEOUT' | 'RESOURCE_LIMIT' | 'FAIL'."""
    s = (arm.get("stages") or {}).get(stage)
    if not s or not s.get("ran"):
        return None
    if s.get("timed_out"):
        return "TIMEOUT"
    if s.get("oom"):
        return "RESOURCE_LIMIT"
    if stage == "test":
        runs = s.get("runs") or []
        if any(r.get("timed_out") for r in runs):
            return "TIMEOUT"
        if any(r.get("oom") for r in runs):
            return "RESOURCE_LIMIT"
        return "FAIL" if any(r.get("exit_code") != 0 for r in runs) else None
    if stage == "peer":
        return None  # peer is judged by comparison with B0, never by its own exit code
    if stage == "audit":
        return None  # audit is judged by comparison with B0 (parsed counts), not exit code alone
    return "FAIL" if s.get("exit_code") != 0 else None


def test_pass_flags(arm: dict) -> List[bool]:
    s = (arm.get("stages") or {}).get("test") or {}
    return [(r.get("exit_code") == 0 and not r.get("timed_out") and not r.get("oom"))
            for r in (s.get("runs") or [])]


def test_status(arm: dict) -> str:
    """'PASS' | 'FAIL' | 'FLAKY' | 'NOT_RUN' over an arm's test runs (both arms run twice)."""
    return b0_test_status(arm)


def b0_test_status(b0: dict) -> str:
    """'PASS' | 'FAIL' | 'FLAKY' | 'NOT_RUN' -- B0 tests are run twice (frozen)."""
    flags = test_pass_flags(b0)
    if not flags:
        return "NOT_RUN"
    if all(flags):
        return "PASS"
    if not any(flags):
        return "FAIL"
    return "FLAKY"


_AUDIT_PATTERNS = {
    "verified_registry_signatures": r"(\d+)\s+packages?\s+(?:have|has)\s+verified\s+registry\s+signatures?",
    "verified_attestations": r"(\d+)\s+packages?\s+(?:have|has)\s+verified\s+attestations?",
    "invalid": r"(\d+)\s+packages?\s+(?:have|has)\s+invalid\s+(?:registry\s+)?signatures?",
    "missing": r"(\d+)\s+packages?\s+(?:have|has)\s+missing\s+(?:registry\s+)?signatures?",
}


def parse_audit_signatures(text: str) -> dict:
    """Parse the human-readable `npm audit signatures` summary.

    IMPORTANT (declared, not hidden): these regexes encode the summary-line
    format as documented for npm 9.5+; they have NOT been validated against
    real worker output yet (the Sigstore TUF CDN is unreachable from the
    session that wrote this). `parse_ok` is False unless at least one
    recognized count was found, and a False is surfaced in the record
    (audit_parse_ok) rather than silently treated as "no change". Confirming
    or correcting this parser against real output is an explicit micro-pilot
    task (docs/phase3_protocol.md Section 8).
    """
    out = {"parse_ok": False, "verified_registry_signatures": 0, "verified_attestations": 0,
           "invalid": 0, "missing": 0}
    if not text:
        return out
    for key, pat in _AUDIT_PATTERNS.items():
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            out[key] = int(m.group(1))
            out["parse_ok"] = True
    return out


def audit_parsed(arm: dict) -> dict:
    s = (arm.get("stages") or {}).get("audit") or {}
    return parse_audit_signatures((s.get("stdout_tail") or "") + "\n" + (s.get("stderr_tail") or ""))


def peer_problems(arm: dict) -> set:
    s = (arm.get("stages") or {}).get("peer") or {}
    return set(s.get("problems") or [])


def tree_diff(b0: dict, pdr: dict) -> Dict[str, Tuple[Optional[str], Optional[str]]]:
    a, b = b0.get("tree_versions") or {}, pdr.get("tree_versions") or {}
    return {k: (a.get(k), b.get(k)) for k in set(a) | set(b) if a.get(k) != b.get(k)}


# ------------------------------------------------------------ pair classification

def classify_pair(b0: dict, pdr: dict) -> dict:
    """Classify one candidate from its paired (B0, PDR) arm records.

    Returns:
      outcome          first failing stage's outcome, else OK / NO_BEHAVIORAL_CHANGE
      failure_stage    that stage's name, or None
      attributable     {stage: bool} -- True iff a PDR failure at that stage
                       could be blamed on the substitution (B0 passed it).
      b0_test_status   PASS | FAIL | FLAKY | NOT_RUN
      audit_parse_ok   False if either arm's audit output was unparseable
      attestation_gain PDR verified_attestations minus B0's (the INTENDED
                       effect of recovery; also an independent check of the
                       dist.attestations classifier -- methodology_freeze S9)
      tree_diff_size   number of installed packages whose version differs
    """
    attributable = {s: True for s in STAGES}
    b0_kind = {s: stage_kind(b0, s) for s in STAGES}
    for s in ("resolve",):
        attributable[s] = True  # B0 has no resolve stage; PDR-only step
    for s in ("install", "lifecycle"):
        attributable[s] = b0_kind[s] is None and stage_ran(b0, s)
    # later stages need B0 to have reached them at all
    attributable["peer"] = stage_ran(b0, "peer") and b0_kind["install"] is None
    attributable["audit"] = stage_ran(b0, "audit") and b0_kind["install"] is None
    tstat = b0_test_status(b0)
    pstat = test_status(pdr)
    attributable["test"] = (tstat == "PASS") and pstat != "FLAKY"

    ap = audit_parsed(b0)
    aq = audit_parsed(pdr)
    audit_parse_ok = (ap["parse_ok"] and aq["parse_ok"]) if (stage_ran(b0, "audit") and stage_ran(pdr, "audit")) else None
    gain = (aq["verified_attestations"] - ap["verified_attestations"]) if audit_parse_ok else None
    diff = tree_diff(b0, pdr)

    outcome, fail_stage = None, None
    for s in STAGES:
        if s == "peer":
            if stage_ran(pdr, "peer") and (peer_problems(pdr) - peer_problems(b0)):
                outcome, fail_stage = sb.PEER_CONFLICT, s
                break
            continue
        if s == "audit":
            if audit_parse_ok and (aq["invalid"] > ap["invalid"] or aq["missing"] > ap["missing"]):
                outcome, fail_stage = AUDIT_SIGNATURE_CHANGE, s
                break
            continue
        if s == "test" and test_status(pdr) == "FLAKY" and stage_kind(pdr, s) == "FAIL":
            outcome, fail_stage = TEST_FLAKY, s
            break
        kind = stage_kind(pdr, s)
        if kind is None:
            continue
        if kind == "TIMEOUT":
            outcome = sb.TIMEOUT
        elif kind == "RESOURCE_LIMIT":
            outcome = sb.RESOURCE_LIMIT
        else:
            stderr = ((pdr.get("stages") or {}).get(s) or {}).get("stderr_tail", "") or ""
            outcome = sb.PEER_CONFLICT if (s in ("resolve", "install") and "eresolve" in stderr.lower()) \
                else _STAGE_FAIL_OUTCOME[s]
        fail_stage = s
        break

    if outcome is None:
        outcome = sb.NO_BEHAVIORAL_CHANGE if not diff and stage_ran(pdr, "install") else sb.OK

    return {
        "outcome": outcome,
        "failure_stage": fail_stage,
        "attributable": attributable,
        "b0_test_status": tstat,
        "pdr_test_status": pstat,
        "audit_parse_ok": audit_parse_ok,
        "attestation_gain": gain,
        "tree_diff_size": len(diff),
    }


# ------------------------------------------------------------------ validation

REQUIRED_KEYS = ["schema_version", "edge_id", "repo", "dep_name", "resolved_version",
                 "candidate_version", "size_bucket", "patch_mode", "pinned_sha", "image_id",
                 "b0", "pdr"]


def validate_record(rec: dict) -> List[str]:
    problems = [f"missing key: {k}" for k in REQUIRED_KEYS if k not in rec]
    if rec.get("schema_version") not in (None, SCHEMA_VERSION):
        problems.append(f"schema_version {rec.get('schema_version')!r} != {SCHEMA_VERSION!r}")
    for arm_name in ("b0", "pdr"):
        arm = rec.get(arm_name)
        if not isinstance(arm, dict) or "stages" not in arm:
            problems.append(f"{arm_name}: missing 'stages'")
            continue
        for st in arm["stages"]:
            if st not in STAGES:
                problems.append(f"{arm_name}: unknown stage {st!r}")
    c = rec.get("classification")
    if c and c.get("outcome") not in OUTCOMES:
        problems.append(f"unknown outcome {c.get('outcome')!r}")
    return problems


# ------------------------------------------------------------------- analysis

def funnel(records: List[dict]) -> List[dict]:
    """Attrition funnel over attributable candidates. Each row's denominator is
    the set of candidates that (a) passed every earlier stage and (b) whose
    result at this stage is attributable to the substitution. Reports the
    attrition at every layer rather than one final percentage."""
    rows = []
    alive = list(records)
    labels = {"resolve": "C0 resolves in worker", "install": "C1 structurally installable",
              "lifecycle": "C1b lifecycle scripts complete", "peer": "C2 no new peer problem",
              "audit": "C3 audit-signature status preserved", "test": "C4 tests do not newly fail"}
    for s in STAGES:
        cl = [(r, classify_pair(r["b0"], r["pdr"])) for r in alive]
        denom = [(r, c) for r, c in cl if c["attributable"][s]]
        passed = [(r, c) for r, c in denom if c["failure_stage"] != s]
        rows.append({"stage": s, "label": labels[s], "entering": len(alive),
                     "attributable": len(denom), "passed": len(passed),
                     "failed": len(denom) - len(passed),
                     "pass_rate": (len(passed) / len(denom)) if denom else None})
        # survivors carry forward: everything not failing THIS stage (non-attributable ones stay alive)
        alive = [r for r, c in cl if c["failure_stage"] != s]
    return rows


def _stage_fail(arm: dict, stage: str, rec_classification: Optional[dict] = None) -> Optional[bool]:
    """True/False if the arm reached and failed/passed the stage; None if indeterminate."""
    if not stage_ran(arm, stage):
        return None
    if stage == "test":
        flags = test_pass_flags(arm)
        return None if not flags else (not all(flags))
    if stage in ("peer", "audit"):
        # Both are judged by comparison with B0, never by the arm's own exit
        # code (stage_kind returns None for them), so a per-arm pass/fail is
        # indeterminate. Returning False here made paired_delta(..., "audit")
        # report every pair as passing on both arms (found 2026-10-05).
        return None
    return stage_kind(arm, stage) is not None


def paired_delta(records: List[dict], stage: str, n_boot: int = 5000, seed: int = 20260928) -> dict:
    """Paired failure-rate delta (PDR - B0) for `stage`, over pairs where BOTH
    arms reached the stage with a determinate result (and, for tests, B0 is
    not flaky). b = B0 pass & PDR fail ("new failure"); c = B0 fail & PDR pass
    ("fix"). delta = (b - c) / n. CI: repository-clustered percentile
    bootstrap (edges within a repo are not independent -- same estimand
    discipline as Phase 1, docs/methodology_freeze.md Section 3)."""
    pairs = []
    for r in records:
        if stage == "test" and (b0_test_status(r["b0"]) == "FLAKY" or test_status(r["pdr"]) == "FLAKY"):
            continue
        f0, f1 = _stage_fail(r["b0"], stage), _stage_fail(r["pdr"], stage)
        if f0 is None or f1 is None:
            continue
        pairs.append((r["repo"], f0, f1))
    n = len(pairs)
    b = sum(1 for _, f0, f1 in pairs if (not f0) and f1)
    c = sum(1 for _, f0, f1 in pairs if f0 and (not f1))
    out = {"stage": stage, "n_pairs": n, "new_failures_b": b, "fixes_c": c,
           "pdr_failure_rate": (sum(1 for *_, f1 in pairs if f1) / n) if n else None,
           "b0_failure_rate": (sum(1 for _, f0, _f in pairs if f0) / n) if n else None,
           "delta": ((b - c) / n) if n else None, "ci95": None, "n_repos": len({p[0] for p in pairs})}
    repos = sorted({p[0] for p in pairs})
    if n and len(repos) >= 2:
        by_repo: Dict[str, List[tuple]] = {}
        for p in pairs:
            by_repo.setdefault(p[0], []).append(p)
        rng = random.Random(seed)
        boots = []
        for _ in range(n_boot):
            sample = [by_repo[repos[rng.randrange(len(repos))]] for _ in repos]
            flat = [p for grp in sample for p in grp]
            m = len(flat)
            bb = sum(1 for _, f0, f1 in flat if (not f0) and f1)
            cc = sum(1 for _, f0, f1 in flat if f0 and (not f1))
            boots.append((bb - cc) / m)
        boots.sort()
        out["ci95"] = [boots[int(0.025 * (len(boots) - 1))], boots[int(round(0.975 * (len(boots) - 1)))]]
    return out


def outcome_counts(records: List[dict]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in records:
        o = classify_pair(r["b0"], r["pdr"])["outcome"]
        out[o] = out.get(o, 0) + 1
    return out
