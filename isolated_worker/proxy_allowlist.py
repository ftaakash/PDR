"""
isolated_worker/proxy_allowlist.py

mitmproxy addon: the ONLY thing standing between a worker container and the
open internet. Workers are on a docker --internal network (no route to the
outside world at all except through this proxy container, which straddles
the internal network and the host's normal network). This addon then
enforces a second, independent layer: even proxied, only these exact hosts
are permitted.

Run with: mitmdump -s isolated_worker/proxy_allowlist.py --mode regular \
    --listen-port 8888 --set block_global=false

ALLOWLIST is intentionally short. Extending it (e.g. to a specific CI
artifact host for a future repo) is a deliberate, reviewable one-line change
here -- never inferred from what a candidate happens to request.
"""
from mitmproxy import http, ctx

ALLOWLIST = {
    "registry.npmjs.org",
    "tuf-repo-cdn.sigstore.dev",     # npm audit signatures' TUF trust root -- see docs/phase2_layer2_results.md
    "fulcio.sigstore.dev",           # only reachable if some future check needs live cert issuance; unused by
    "rekor.sigstore.dev",            # `npm audit signatures` itself, kept for completeness/documented parity
}


def _host(flow: http.HTTPFlow) -> str:
    return (flow.request.pretty_host or "").lower()


def request(flow: http.HTTPFlow) -> None:
    host = _host(flow)
    if host not in ALLOWLIST:
        msg = f'refused on filtered domain "{host}"'
        ctx.log.warn(msg)   # written to `docker logs pdr-proxy`; orchestrate.py's parse_denied_hosts() reads this
        flow.response = http.Response.make(403, b"", {"X-PDR-Proxy": msg})
        return
    if flow.request.method not in ("GET", "HEAD", "POST"):
        msg = f'refused method "{flow.request.method}" on "{host}"'
        ctx.log.warn(msg)
        flow.response = http.Response.make(403, b"", {"X-PDR-Proxy": msg})
