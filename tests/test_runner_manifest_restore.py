"""Protocol Section 12: the PDR arm's tests see the byte-identical original package.json."""
import importlib.util
import json
import os
import sys
import types

# runner.py imports the Unix-only `resource` module; stub it so the pure helper can be
# tested on any host (the real module is present inside the Linux worker).
sys.modules.setdefault("resource", types.ModuleType("resource")) if os.name == "nt" else None

path = os.path.join(os.path.dirname(__file__), "..", "isolated_worker", "runner.py")
spec = importlib.util.spec_from_file_location("runner", path)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)   # import only; main() refuses outside the worker image


def test_restore_manifest_is_byte_identical(tmp_path):
    original = b'{\n  "name": "x",\n  "devDependencies": {"a": "^1.0.0"}\n}\n'
    pj = tmp_path / "package.json"
    pj.write_bytes(original)
    pj.write_text(json.dumps({"name": "x", "devDependencies": {"a": "^1.0.0"}, "overrides": {"a": "1.2.3"}}))
    assert runner.restore_manifest(str(tmp_path), original)
    assert pj.read_bytes() == original


def test_runner_restores_only_for_pdr_and_before_tests():
    src = open(path, encoding="utf-8").read()
    i_restore = src.index("restore_manifest(work, original_manifest)")
    assert src.index('go("audit"') < i_restore < src.index('for _ in range(spec["test_runs"])')
    assert 'if arm == "pdr":\n            # Section 12' in src
    assert "--max-old-space-size=6144" in src
