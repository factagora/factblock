"""examples/promises: promises and verdicts from one CSV, read as of four dates: open, past due with no
verdict, broken, kept. Rebuilds the bundle from the CSV so the example and its data cannot drift.
Run: uv run python tests/test_promises_example.py"""
import pathlib
import runpy
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import factblock  # noqa: E402

EX = ROOT / "examples" / "promises"
with tempfile.TemporaryDirectory() as d:
    brain = pathlib.Path(d) / "brain"
    subprocess.run([sys.executable, "-m", "factblock", "import", str(EX / "promises.csv"), "--backfill", "-o", str(brain)], check=True, capture_output=True)
    committed = factblock.Bundle(EX / "brain")
    assert sorted(n["id"] for n in factblock.Bundle(brain).nodes) == sorted(n["id"] for n in committed.nodes) == ["p1", "p2", "p3"]
assert all(c.ok for c in factblock.validate(EX / "brain"))

status = runpy.run_path(str(EX / "run.py"))["status"]
assert status("2026-03-15", "Globex") == {"p1": "open", "p3": "open"}
assert status("2026-04-01")["p2"] == "past due"
assert [i["id"] for i in factblock.recall(EX / "brain", "", "2026-04-01", verdict="overdue")["items"]] == ["p2"]
assert factblock.recall(EX / "brain", "", "2026-04-10", verdict="overdue")["items"] == []   # broken by then
assert status("2026-04-10") == {"p1": "open", "p2": "broken", "p3": "open"}
assert status("2026-05-10") == {"p1": "kept", "p2": "broken", "p3": "open"}
ctx = factblock.context(EX / "brain", "Globex", "2026-05-10")
assert "(due 2026-06-30)" in ctx and "  verdict: kept (decided 2026-05-03 by human:lee)" in ctx, ctx
import json  # noqa: E402
cr = json.dumps(factblock.to_claimreview(EX / "brain", "2026-05-10"))
assert '"Kept"' in cr and '"Broken"' in cr, cr
print("PASS promises example: open, past due without a verdict, broken, kept, each as of its date")
