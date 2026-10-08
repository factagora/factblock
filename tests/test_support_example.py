"""examples/support-agent: five dated support questions. A date filter puts a stale statement into the
prompt (or misses the verdict) on all five; factblock.context() on none. Also: a promise stays in recall,
marked ended, once its deadline passes and it is settled. Run: uv run python tests/test_support_example.py"""
import pathlib
import runpy
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import factblock  # noqa: E402

ex = runpy.run_path(str(ROOT / "examples" / "support-agent" / "run.py"))
res = ex["evaluate"]()
assert [r["date_filter"]["pass"] for r in res] == [False] * 5, [(r["id"], r["date_filter"]["why"]) for r in res]
assert [r["factblock"]["pass"] for r in res] == [True] * 5, [(r["id"], r["factblock"]["why"]) for r in res]
assert all(c.ok for c in factblock.validate(ROOT / "examples" / "support-agent" / "brain"))

brain = ROOT / "examples" / "support-agent" / "brain"
before = {i["id"]: i for i in factblock.recall(brain, "SSO customer A", "2026-06-15")["items"]}
assert "ended" not in before["sso-promise"] and "verdict" not in before["sso-promise"]      # still open, not settled
after = {i["id"]: i for i in factblock.recall(brain, "SSO customer A", "2026-07-05")["items"]}
assert after["sso-promise"]["verdict"]["outcome"] == "did_not" and after["sso-promise"]["ended"].isoformat().startswith("2026-06-30")
print("PASS support example: date filter 0/5, factblock 5/5; a settled promise stays in recall, marked ended")
