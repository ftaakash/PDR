"""
pdr.regression
================
SECONDARY, independently-killable per README ("Regression bonus only";
"kill independently"). This module must never be used to rescue a weak
primary result -- if it contributes nothing, analyze_kill.py must still be
able to report a GO/KILL verdict on gate criteria A/B/(C)/(D)/E/F without it.

What this computes (fully real, from data already fetched by
check_provenance.py -- no extra network calls):
    For each package name, sort its published versions chronologically using
    the registry packument's `time` map. Walk the sequence and flag every
    adjacent pair (v_i -> v_{i+1}) where has_provenance goes True -> False.
    That is a REGRESSION EVENT. This measures "provenance loss over time",
    the secondary RQ4 signal in the audit prompt.

What this deliberately does NOT compute in the pilot (declared limitation,
not silently skipped): builder/source-path identity change enrichment.
The npm attestations endpoint (verified reachable --
https://registry.npmjs.org/-/npm/v1/attestations/{name}@{version}) carries a
second SLSA-provenance predicate with repository/workflow identity that
could, in principle, distinguish "lost provenance because the maintainer
reverted" from "provenance moved because the build pipeline changed". Fetching
that is a SECOND HTTP call PER VERSION (not per package), which is 10-50x the
request volume of everything else in this pipeline combined. `fetch_attestation_bundle()`
below is included as the entry point for that Phase 2 work but is not called
by scan_regression.py's default pilot run -- see docs/gate_status.md, Kill Test 9.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import List, Optional

from pdr.provenance import Packument, USER_AGENT, _encode_name

ATTESTATIONS_BASE = "https://registry.npmjs.org/-/npm/v1/attestations"


@dataclass
class RegressionEvent:
    package: str
    from_version: str
    to_version: str
    from_time: Optional[str]
    to_time: Optional[str]


def scan_package_regressions(pk: Packument) -> List[RegressionEvent]:
    """Return regression events for one package, or [] if not computable
    (NA handling: a package with <2 versions carrying a usable publish time
    cannot show a transition, and is reported as NA by the caller, not as
    "zero regressions" -- those are different claims)."""
    dated = [(v, vf) for v, vf in pk.versions.items() if vf.time is not None]
    if len(dated) < 2:
        return []
    dated.sort(key=lambda x: x[1].time)

    events: List[RegressionEvent] = []
    for (v_prev, f_prev), (v_next, f_next) in zip(dated, dated[1:]):
        if f_prev.has_provenance and not f_next.has_provenance:
            events.append(RegressionEvent(
                package=pk.name,
                from_version=v_prev, to_version=v_next,
                from_time=f_prev.time, to_time=f_next.time,
            ))
    return events


def package_regression_status(pk: Packument) -> str:
    """"regressed" | "no_regression" | "NA" -- explicit NA handling per
    tests/test_regression_na.py. NA means: not enough dated version history
    to say anything, which is NOT the same as "confirmed no regression"."""
    dated = [(v, vf) for v, vf in pk.versions.items() if vf.time is not None]
    if len(dated) < 2:
        return "NA"
    return "regressed" if scan_package_regressions(pk) else "no_regression"


def fetch_attestation_bundle(name: str, version: str, timeout: int = 20) -> Optional[dict]:
    """Phase-2 entry point (NOT called by the default pilot run -- see module
    docstring). Fetches the raw attestation bundle for one exact version,
    which is where builder/repository identity for source-path-change
    enrichment would come from."""
    url = f"{ATTESTATIONS_BASE}/{_encode_name(name)}@{version}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
