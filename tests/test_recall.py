"""The one check that fails if recall breaks: ranked by hits, masked by as_of, kinds filtered,
and context() is prompt-ready lines. Run: uv run python tests/test_recall.py"""
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import factblock  # noqa: E402

RATES = pathlib.Path(__file__).resolve().parents[1] / "samples" / "rates"
ids = lambda r: [i["id"] for i in r["items"]]  # noqa: E731

r = factblock.recall(RATES, "interest rates", "2024-10-01")
assert ids(r)[:2] == ["c4", "c1"] and r["items"][0]["score"] == 2, r["items"]          # both terms hit; newest first
assert "c2" in ids(r) and r["matched"] == 3, ids(r)                                   # "rate hike" matches by prefix
may = factblock.recall(RATES, "interest rates", "2024-05-01")
assert ids(may) == ["c1", "c2"] and may["certificate"]["masked"]["node"] == 4, may      # c4 is not known yet
assert factblock.recall(RATES, "TSLA", "2024-08-01")["items"] == []                   # not known yet
assert ids(factblock.recall(RATES, "TSLA", "2024-10-01")) == ["t1", "t2"]
assert factblock.recall(RATES, "housing", "2024-10-01", limit=1)["matched"] == 1
assert factblock.recall(RATES, "nothing here", "2024-10-01")["items"] == []
ctx = factblock.context(RATES, "interest rates", "2024-05-01")
assert ctx.startswith("- 2024-03-20: The Fed raises interest rates") and "later blocks hidden" in ctx, ctx
out = subprocess.run([sys.executable, "-m", "factblock", "recall", str(RATES), "rates", "--as-of", "2024-10-01"], capture_output=True, text=True, check=True).stdout
assert out.startswith("c4") and "of 3 matching" in out, out
print("PASS recall: ranked by hits and recency, masked by as_of, limit, context lines, CLI")
