"""Allowlist decisions of isolated_worker/proxy_allowlist.py (CONNECT-level filtering, 2026-10-05)."""
import importlib.util
import os
import re

path = os.path.join(os.path.dirname(__file__), "..", "isolated_worker", "proxy_allowlist.py")
spec = importlib.util.spec_from_file_location("proxy_allowlist", path)
pa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pa)


def test_allowlist_is_exactly_the_documented_four_hosts():
    assert pa.ALLOWLIST == {"registry.npmjs.org", "tuf-repo-cdn.sigstore.dev",
                            "fulcio.sigstore.dev", "rekor.sigstore.dev"}


def test_exact_match_only():
    assert pa.host_allowed("registry.npmjs.org")
    assert pa.host_allowed("Registry.NPMJS.org.")          # case and trailing dot normalised
    for bad in ["example.com", "registry.npmjs.org.evil.net", "evil-registry.npmjs.org",
                "npmjs.org", "sub.registry.npmjs.org", "", None]:
        assert not pa.host_allowed(bad), bad


def test_connect_refusal_wording_matches_orchestrator_parser():
    msg = pa.refusal_reason("example.com", "CONNECT")
    denied = re.compile(r'refused on filtered domain "?([^"\s]+)"?', re.I)   # orchestrate._DENIED
    assert denied.search(msg).group(1) == "example.com"
    assert pa.refusal_reason("registry.npmjs.org", "CONNECT") is None


def test_plain_http_still_filters_methods():
    assert pa.refusal_reason("registry.npmjs.org", "GET") is None
    assert pa.refusal_reason("registry.npmjs.org", "POST") is None
    assert "refused method" in pa.refusal_reason("registry.npmjs.org", "PUT")
    assert "refused method" in pa.refusal_reason("registry.npmjs.org", "DELETE")
    assert "filtered domain" in pa.refusal_reason("example.com", "GET")


def test_tls_is_never_intercepted():
    class Data:
        ignore_connection = False
    d = Data()
    pa.tls_clienthello(d)
    assert d.ignore_connection is True
