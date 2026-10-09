"""examples/analysis: the three views over samples/cramer agree with the Python reader, every mark carries
a FactBlock id and a source, links are labelled as recorded, and the template CSV runs through the same
views. Run: uv run python tests/test_analysis_example.py"""
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "examples" / "analysis"))
import factblock  # noqa: E402
import views  # noqa: E402

AS_OF = "2026-09-10"
con, pq = views.connect(ROOT / "samples" / "cramer")
b = factblock.Bundle(ROOT / "samples" / "cramer")

# stance: every SPY up/down call known by AS_OF, verdicts as the library sees them
s = views.stance(con, pq, "SPY", AS_OF)
want = [n for n in b.nodes if n["kind"] == "prediction" and (n.get("payload") or {}).get("asset") == "SPY"
        and n["payload"].get("direction") in ("up", "down")]
assert sorted(r["id"] for r in s["rows"]) == sorted(n["id"] for n in want)
lib = {i["id"]: i.get("verdict", {}).get("outcome") for i in factblock.recall(b, "", AS_OF, kinds=("prediction",), limit=5000)["items"]}
for r in s["rows"]:
    assert r["url"].startswith("https://www.youtube.com/") and r["id"]
    if r["id"] in lib and lib[r["id"]]:
        assert r["outcome"] == lib[r["id"]], r
assert {r["status"] for r in s["rows"]} == {"came true", "did not", "no verdict", "replaced"}
assert s["spec"]["encoding"]["href"] == {"field": "url"}

# evidence: one statement, its recorded links, nothing learned later
e = views.evidence(con, pq, "fdc79a63b9b44a7f", AS_OF)
assert len(e["links"]) == 5 and all(l["basis"].startswith("recorded") for l in e["links"])
assert next(r for r in e["rows"] if r["id"] == "ba4c1a04d78f5848")["status"] == "did not"
early = views.evidence(con, pq, "fdc79a63b9b44a7f", "2025-03-22")   # the 03-25 follow-up was not said yet
assert "ba4c1a04d78f5848" not in {r["id"] for r in early["rows"]} and len(early["links"]) == 4

# status: segments add up to the calls per subject, and the ids behind each segment are real blocks
st = views.status(con, pq, AS_OF)
spy = {r["status"]: r for r in st["rows"] if r["subject"] == "SPY"}
assert sum(r["n"] for r in spy.values()) == 49 and all(len(r["ids"]) == r["n"] for r in spy.values())
ids = {n["id"] for n in b.nodes}
assert all(i in ids for r in st["rows"] for i in r["ids"])

assert [views.pick(q) for q in ("Why is he bullish?", "When did his view change?", "How accurate is he overall?")] == ["evidence", "stance", "status"]

# your own data: the template CSV through import and the same views
with tempfile.TemporaryDirectory() as d:
    subprocess.run([sys.executable, "-m", "factblock", "import", str(ROOT / "examples" / "analysis" / "template.csv"), "--backfill", "-o", d + "/b"], check=True, capture_output=True)
    c2, p2 = views.connect(d + "/b")
    assert [(r["id"], r["status"]) for r in views.stance(c2, p2, "ACME", "2026-06-01")["rows"]] == [("c1", "replaced"), ("c2", "came true")]
print("PASS analysis example: stance, evidence and status views match the reader; ids and sources on every mark; links marked recorded; template CSV runs")
