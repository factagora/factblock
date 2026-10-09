"""examples/analysis: the three findings (track record as known vs hindsight, reversals, reasons) and the two
drill-downs over samples/cramer agree with the Python reader, every mark carries
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

# backtest: the as-of rule reads only verdicts known before each call; the hindsight rule reads them all
bt = views.backtest(con, pq, AS_OF)
sm = bt["summary"]
assert sm["every call"]["calls"] == 779 and sm["rule, picked with hindsight"]["calls"] == 209 and sm["rule, picked as of each call"]["calls"] == 75
assert sm["rule, picked with hindsight"]["per_call"] > sm["every call"]["per_call"] > sm["rule, picked as of each call"]["per_call"]
assert bt["title"].startswith("Following only his best subjects looks like +9.3% a call.")

# track record: the as-known line uses only verdicts known by each day, the hindsight line every verdict on calls made by then
tr = views.track_record(con, pq, AS_OF)
jul = next(r for r in tr["rows"] if r["day"] == "2025-07-01")
known = [r for r in b.resolutions if r["known_at"] < factblock.bundle.parse_instant("2025-07-01")]
assert jul["known"] == len(known) and abs(jul["known_rate"] - sum(r["outcome"] == "came_true" for r in known) / len(known)) < 1e-9
asserted = {n["id"]: n["asserted_at"] for n in b.nodes}
hind = [r for r in b.resolutions if asserted[r["target_id"]] < factblock.bundle.parse_instant("2025-07-01")]
assert jul["hindsight"] == len(hind) and jul["future"] == len(hind) - len(known) > 0
assert tr["title"].startswith("On 1 Jul 2025 his record read 46%.")

# reversals: every SUPERSEDES row counted once; the four settled outcomes plus the unsettled add up
rv = views.reversals(con, pq, AS_OF)
assert rv["total"] == sum(1 for e in b.edges if e["edge_type"] == "SUPERSEDES") == 108
assert {r["outcome"]: r["n"] for r in rv["rows"]} == {"fixed a wrong call": 10, "broke a right call": 10, "both right": 17, "both wrong": 12}
assert all(len(r["pairs"]) == r["n"] for r in rv["rows"])

# reasons: the two groups partition the settled predictions
rs = views.reasons(con, pq, AS_OF)
settled = {r["target_id"] for r in b.resolutions} & {n["id"] for n in b.nodes if n["kind"] == "prediction"}
assert sum(r["settled"] for r in rs["rows"]) == len(settled) and set().union(*(set(r["ids"]) for r in rs["rows"])) == settled

assert [views.pick(q) for q in ("Why is he bullish?", "When did his view change?", "How accurate is he overall?")] == ["evidence", "stance", "track_record"]
assert views.pick("What if I had followed his calls?") == "backtest"

# your own data: the template CSV through import and the same views
with tempfile.TemporaryDirectory() as d:
    subprocess.run([sys.executable, "-m", "factblock", "import", str(ROOT / "examples" / "analysis" / "template.csv"), "--backfill", "-o", d + "/b"], check=True, capture_output=True)
    c2, p2 = views.connect(d + "/b")
    assert [(r["id"], r["status"]) for r in views.stance(c2, p2, "ACME", "2026-06-01")["rows"]] == [("c1", "replaced"), ("c2", "came true")]
    assert views.reversals(c2, p2, "2026-06-01")["total"] == 1
print("PASS analysis example: backtest (as of vs hindsight), track record (as known vs hindsight), reversals, reasons, stance and evidence match the reader; ids and sources on every mark; links marked recorded; template CSV runs")
