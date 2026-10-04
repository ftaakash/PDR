"""
tests/test_isolated_worker.py
These tests exist because isolated_worker/orchestrate.py is the one place
this project could execute untrusted code unsafely if its guardrails ever
regressed. Nothing here needs a docker daemon: build_docker_run_command and
assert_command_safe are pure functions over argv lists, tested against both
the real construction path (must pass) and deliberately mutilated commands
(must be rejected). This is the safety-critical counterpart to
tests/test_layer1_patch_logic.py's correctness focus.
"""
import copy
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from isolated_worker.orchestrate import (  # noqa: E402
    build_docker_run_command, assert_command_safe, canonical_sha256, verify_manifest,
    parse_denied_hosts, evaluate_selftest, CFG,
)

SPEC = {"arm": "pdr", "experiment": {"dep_name": "x", "candidate_version": "1.0.0"},
        "test_command": "npm test", "timeouts": {}, "tail_bytes": 4000, "test_runs": 1}


def real_cmd():
    return build_docker_run_command("pdr-test-1", "/abs/path/to/snapshot", SPEC)


def test_real_construction_passes_the_safety_gate():
    assert_command_safe(real_cmd())  # must not raise


def test_missing_cap_drop_is_rejected():
    cmd = [a for a in real_cmd() if a != "--cap-drop=ALL"]
    try:
        assert_command_safe(cmd)
        assert False, "should have raised"
    except AssertionError as e:
        assert "cap-drop" in str(e)


def test_missing_read_only_is_rejected():
    cmd = [a for a in real_cmd() if a != "--read-only"]
    try:
        assert_command_safe(cmd)
        assert False, "should have raised"
    except AssertionError:
        pass


def test_privileged_flag_is_rejected_even_if_everything_else_is_fine():
    cmd = real_cmd() + ["--privileged"]
    try:
        assert_command_safe(cmd)
        assert False, "should have raised"
    except AssertionError as e:
        assert "privileged" in str(e)


def test_host_network_is_rejected():
    cmd = [("--network=host" if a.startswith("--network=") else a) for a in real_cmd()]
    try:
        assert_command_safe(cmd)
        assert False, "should have raised"
    except AssertionError:
        pass


def test_docker_socket_mount_is_rejected():
    cmd = real_cmd() + ["--mount", "type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock"]
    try:
        assert_command_safe(cmd)
        assert False, "should have raised"
    except AssertionError as e:
        assert "docker.sock" in str(e) or "expected exactly 1 mount" in str(e)


def test_extra_writable_mount_is_rejected():
    cmd = real_cmd() + ["--mount", "type=bind,source=/etc,target=/etc-host"]
    try:
        assert_command_safe(cmd)
        assert False, "should have raised"
    except AssertionError as e:
        assert "exactly 1 mount" in str(e)


def test_snapshot_mount_must_be_readonly():
    cmd = [a.replace(",readonly", "") if a.startswith("type=bind,") else a for a in real_cmd()]
    try:
        assert_command_safe(cmd)
        assert False, "should have raised"
    except AssertionError as e:
        assert "read-only" in str(e).lower()


def test_credential_like_env_var_is_rejected():
    cmd = real_cmd() + ["-e", "NPM_AUTH_TOKEN=deadbeef"]
    try:
        assert_command_safe(cmd)
        assert False, "should have raised"
    except AssertionError as e:
        assert "credential" in str(e)


def test_cap_add_is_rejected():
    cmd = real_cmd() + ["--cap-add=SYS_ADMIN"]
    try:
        assert_command_safe(cmd)
        assert False, "should have raised"
    except AssertionError as e:
        assert "cap-add" in str(e)


def test_spec_json_is_passed_via_env_not_argv_injection():
    # the experiment dict is JSON-embedded in one -e value, not interpolated
    # into the shell/argv in a way that could break out of it
    cmd = real_cmd()
    spec_env = next(cmd[i + 1] for i, a in enumerate(cmd) if a == "-e" and cmd[i + 1].startswith("PDR_SPEC="))
    parsed = json.loads(spec_env[len("PDR_SPEC="):])
    assert parsed == SPEC


def test_manifest_hash_matches_committed_hash():
    m = {"a": 1, "b": [1, 2, 3]}
    h = canonical_sha256(m)
    verify_manifest(m, h)  # must not raise
    verify_manifest(m, h + "\n")  # trailing newline (as a real file would have) tolerated


def test_manifest_hash_mismatch_is_refused():
    m = {"a": 1}
    try:
        verify_manifest(m, "0" * 64)
        assert False, "should have raised"
    except SystemExit:
        pass


def test_manifest_hash_is_order_independent_but_content_sensitive():
    m1, m2 = {"a": 1, "b": 2}, {"b": 2, "a": 1}
    assert canonical_sha256(m1) == canonical_sha256(m2)
    m3 = {"a": 1, "b": 3}
    assert canonical_sha256(m1) != canonical_sha256(m3)


def test_parse_denied_hosts_extracts_from_proxy_log_lines():
    log = 'warn: refused on filtered domain "evil.example.com"\nsome other line\n'
    assert parse_denied_hosts(log) == ["evil.example.com"]


def test_parse_denied_hosts_empty_on_clean_log():
    assert parse_denied_hosts("200 GET https://registry.npmjs.org/foo\n") == []


def test_selftest_passes_only_when_all_checks_hold():
    good = {"registry_via_proxy": "200", "tuf_via_proxy": "200", "denied_via_proxy": "403",
            "direct_registry": "000", "denied_hosts_seen_in_proxy_log": ["example.com"]}
    assert evaluate_selftest(good)["passed"] is True


def test_selftest_fails_if_denied_host_actually_succeeds():
    leaky = {"registry_via_proxy": "200", "tuf_via_proxy": "200", "denied_via_proxy": "200",
             "direct_registry": "000", "denied_hosts_seen_in_proxy_log": []}
    ev = evaluate_selftest(leaky)
    assert ev["passed"] is False and ev["checks"]["denied_host_blocked"] is False


def test_selftest_fails_if_direct_connection_succeeds():
    bypassed = {"registry_via_proxy": "200", "tuf_via_proxy": "200", "denied_via_proxy": "403",
                "direct_registry": "200", "denied_hosts_seen_in_proxy_log": ["example.com"]}
    ev = evaluate_selftest(bypassed)
    assert ev["passed"] is False and ev["checks"]["direct_connection_blocked"] is False


def test_selftest_fails_if_proxy_log_does_not_confirm_the_denial():
    # denied_via_proxy=403 alone isn't enough -- this also validates the
    # assumption parse_denied_hosts() relies on (the log wording) is
    # actually correct, on the FIRST real run rather than being assumed.
    unconfirmed = {"registry_via_proxy": "200", "tuf_via_proxy": "200", "denied_via_proxy": "403",
                   "direct_registry": "000", "denied_hosts_seen_in_proxy_log": []}
    ev = evaluate_selftest(unconfirmed)
    assert ev["passed"] is False and ev["checks"]["denied_host_is_logged"] is False


def test_config_resource_limits_are_finite_and_nonzero():
    assert int(CFG["cpus"]) > 0 or float(CFG["cpus"]) > 0
    assert CFG["memory"].endswith(("g", "m")) and CFG["memory"][:-1].isdigit()
    assert int(CFG["pids"]) > 0
    assert CFG["container_wall_s"] > 0


def test_real_cmd_is_not_mutated_by_repeated_calls():
    c1, c2 = real_cmd(), real_cmd()
    assert c1 == c2
    c1.append("--privileged")
    assert "--privileged" not in real_cmd()
