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

HTTPS handling (amendment 2026-10-05, docs/phase3_protocol.md Section 2.1):
the proxy does NOT decrypt TLS. The allowlist is enforced on the CONNECT
request (the hostname a client asks to tunnel to); refused hosts get a logged
403 before any TLS starts, and allowed tunnels are passed through untouched,
so clients verify the real server certificates. The first real self-test
showed that intercepting TLS made every HTTPS request fail certificate
verification in the worker. Plain-HTTP requests are still checked per request
(host and method).

ALLOWLIST is intentionally short. Extending it (e.g. to a specific CI
artifact host for a future repo) is a deliberate, reviewable one-line change
here -- never inferred from what a candidate happens to request.
"""
try:
    from mitmproxy import http, ctx
except ImportError:  # pure decision logic below stays importable for host-side tests
    http = ctx = None

ALLOWLIST = {
    "registry.npmjs.org",
    "tuf-repo-cdn.sigstore.dev",     # npm audit signatures' TUF trust root -- see docs/phase2_layer2_results.md
    "fulcio.sigstore.dev",           # only reachable if some future check needs live cert issuance; unused by
    "rekor.sigstore.dev",            # `npm audit signatures` itself, kept for completeness/documented parity
}
ALLOWED_PLAIN_HTTP_METHODS = ("GET", "HEAD", "POST")


# ------------------------------------------------------------ pure decisions

def host_allowed(host: str) -> bool:
    """Exact, case-insensitive match; no suffix/wildcard matching, so
    evil-registry.npmjs.org.attacker.net or registry.npmjs.org.evil never pass."""
    return (host or "").strip().lower().rstrip(".") in ALLOWLIST


def refusal_reason(host: str, method: str = "CONNECT") -> "str | None":
    """None if allowed, else the log line. The 'refused on filtered domain'
    wording is what orchestrate.parse_denied_hosts() reads."""
    h = (host or "").strip().lower().rstrip(".")
    if not host_allowed(h):
        return f'refused on filtered domain "{h}"'
    if method != "CONNECT" and method not in ALLOWED_PLAIN_HTTP_METHODS:
        return f'refused method "{method}" on "{h}"'
    return None


# ------------------------------------------------------------ mitmproxy hooks

def _refuse(flow, msg: str) -> None:
    ctx.log.warn(msg)   # written to `docker logs pdr-proxy`
    flow.response = http.Response.make(403, b"", {"X-PDR-Proxy": msg})


def http_connect(flow) -> None:
    """HTTPS: decide on the tunnel's target host before any TLS."""
    msg = refusal_reason(flow.request.host, "CONNECT")
    if msg:
        _refuse(flow, msg)


def tls_clienthello(data) -> None:
    """Never intercept TLS: only allowlisted CONNECTs get this far, and they
    are passed through end to end."""
    data.ignore_connection = True


def request(flow) -> None:
    """Plain HTTP (no tunnel): host and method are both visible, check both."""
    if flow.request.method == "CONNECT":
        return
    msg = refusal_reason(flow.request.pretty_host, flow.request.method)
    if msg:
        _refuse(flow, msg)
