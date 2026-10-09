"""The one check that fails if timeline breaks: lanes carry said / learned / replaced / verdict events as known on
as_of (a re-resolution shows as a second verdict, a later replacement is not drawn early), a series is cut at
as_of, deadlines become spans, and the chart saves as HTML and JSON from the library and the CLI.
Run: uv run python tests/test_timeline.py"""
import datetime
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import factblock  # noqa: E402
import factblock.timeline  # noqa: E402
timeline_mod = sys.modules["factblock.timeline"]

RATES, FFR = ROOT / "samples" / "rates", ROOT / "samples" / "fed-funds-rate.csv"

t = factblock.timeline(RATES, "2025-01-01", "interest rates")
ev = [(e["id"], e["t"], e["event"]) for e in t.events if e["id"] == "c1"]
assert ev == [("c1", "2024-03-20", "said"), ("c1", "2024-04-15", "learned later"), ("c1", "2024-05-01", "verdict: right"),
              ("c1", "2024-09-18", "replaced"), ("c1", "2024-12-01", "verdict: wrong")], ev
assert {c["id"]: c["status"] for c in t.claims}["c1"] == "wrong"
assert all(e["t"] <= "2025-01-01" for e in t.events)

early = factblock.timeline(RATES, "2024-06-01", "interest rates")   # before the cut was said and before the re-resolution
assert {c["id"]: c["status"] for c in early.claims} == {"c1": "right", "c2": "open"}   # c4 not said yet
assert not any(e["event"] == "replaced" for e in early.events)

s = t.with_series(FFR, "Fed funds rate (%)")
assert s.series[-1][0].date().isoformat() <= "2025-01-01" and s.series[0][1] == 5.33
assert s.spec()["layer"][0]["encoding"]["y"]["title"] == "Fed funds rate (%)"
assert [p.get("label") for p in s.spec()["layer"][2]["data"]["values"] if p["id"] == "c1"] == ["The Fed raises interest rates"]   # settled: labelled
try:
    t.with_series([("2030-01-01", 1.0)]); raise AssertionError("a series entirely after as_of must be refused")
except ValueError as e:
    assert "on or before as_of" in str(e)

promises = ROOT / "examples" / "promises" / "brain"
assert {c["id"]: c["status"] for c in factblock.timeline(promises, "2026-04-01").claims} == {"p1": "open", "p2": "open", "p3": "open"}
late = factblock.timeline(promises, "2026-05-10")
assert {c["id"]: (c["status"], c["due"]) for c in late.claims} == {"p1": ("right", "2026-04-30"), "p2": ("wrong", "2026-03-31"), "p3": ("open", "2026-06-30")}
assert {c["id"]: c["end"] for c in late.claims} == {"p1": "2026-04-30", "p2": "2026-03-31", "p3": "2026-06-30"}   # bars end at the deadline
g = factblock.timeline(promises, "2026-05-10", group_by="customer")
assert {c["group"] for c in g.claims} == {"Globex", "Initech"} and g.spec()["facet"]["row"]["field"] == "group"
assert {c["id"]: c["end"] for c in t.claims}["c1"] == "2024-05-01"   # the first thing that happened to it: a verdict

assert [c["id"] for c in factblock.timeline(RATES, "2025-01-01", ids=["c4", "c1"]).claims] == ["c1", "c4"]
try:
    factblock.timeline(RATES, "2024-06-01", ids=["c4"]); raise AssertionError("c4 was not known yet")
except ValueError as e:
    assert "c4" in str(e)

# the data contract: to_dict() names its schema and carries the fields the schema requires
sch = json.loads((ROOT / "schemas" / "timeline.v1.schema.json").read_text())
dd = json.loads(json.dumps(s.to_dict(), default=str))
assert dd["schema"] == sch["properties"]["schema"]["const"] and set(sch["required"]) <= set(dd)
assert all(set(sch["properties"]["claims"]["items"]["required"]) <= set(c) for c in dd["claims"])
assert all(e["event"] in sch["properties"]["events"]["items"]["properties"]["event"]["enum"] for e in dd["events"])
md = t.to_markdown()
assert "The Fed raises interest rates **wrong** (verdict false)" in md and md.rstrip().endswith("nothing learned later is shown._")
assert 'src="https://cdn.jsdelivr.net/npm/vega@5.30.0"' in t.to_html() and "prefers-color-scheme" in t.to_html()

# MCP Apps: a tool result with text for the model, rows, and the spec where only the view reads it; the view speaks the protocol
r = s.to_mcp()
assert r["content"][0]["text"] == s.to_markdown() and r["structuredContent"]["schema"] == "factblock.timeline/v1"
assert r["_meta"]["factblock/vega-lite"]["layer"][0]["mark"]["type"] == "line"
from factblock.timeline import MCP_APP_MIME, MCP_APP_TOOL_META, MCP_APP_URI  # noqa: E402
v = factblock.mcp_app_html()
assert MCP_APP_MIME == "text/html;profile=mcp-app" and MCP_APP_TOOL_META["ui"]["resourceUri"] == MCP_APP_URI.startswith("ui://") * MCP_APP_URI
assert all(x in v for x in ("ui/initialize", '"2026-01-26"', "ui/notifications/initialized", "ui/notifications/tool-result", "ui/notifications/size-changed", "ui/open-link"))

m = t._repr_mimebundle_()
assert "application/vnd.vegalite.v5+json" in m and m["application/vnd.vegalite.v5+json"]["layer"][1]["encoding"]["href"] == {"field": "source"}
assert "2024-12-01 verdict: wrong" in {c["id"]: c["history"] for c in t.claims}["c1"]
with tempfile.TemporaryDirectory() as d:
    d = pathlib.Path(d)
    s.save(d / "t.html"); s.save(d / "t.json"); s.save(d / "t.vl.json")
    assert "vegaEmbed" in (d / "t.html").read_text() and json.loads((d / "t.json").read_text())["series"][0] == {"t": "2024-01-01", "value": 5.33}
    p = subprocess.run([sys.executable, "-m", "factblock", "timeline", str(RATES), "--as-of", "2025-01-01", "-q", "interest rates",
                        "--series", str(FFR), "-o", str(d / "c.html")], capture_output=True, text=True)
    assert p.returncode == 0 and (d / "c.html").exists() and "3 statements" in p.stdout, p.stdout + p.stderr
# a ledger's own words for a verdict read the same: tckg writes hit and miss
assert [timeline_mod._outcome(o) for o in ("hit", "miss", "partial")] == ["right", "wrong", "mixed"]

# labels stop at the chart edge whatever width the host gives it, and the legend sits below
texts = [l["mark"] for l in factblock.timeline(RATES, "2025-01-01").spec()["layer"] if l["mark"]["type"] == "text"]
assert texts and all("expr" in m["limit"] for m in texts), texts
assert factblock.timeline(RATES, "2025-01-01").spec()["config"]["legend"]["orient"] == "bottom"
# series labels: close in time means split by value (never both above), and each is capped to a share of the width
with tempfile.TemporaryDirectory() as d:
    rise = pathlib.Path(d) / "rise.csv"
    rise.write_text("date,v\n" + "".join(f"2024-{m:02d}-01,{m}\n2025-{m:02d}-01,{12 + m}\n" for m in range(1, 13)))
    sp = factblock.timeline(ROOT / "samples" / "cramer", "2025-06-30", "SPY", limit=20).with_series(rise).spec()
pts = [p for p in next(l for l in sp["layer"] if l["mark"]["type"] == "point")["data"]["values"] if p["label"]]
day = lambda p: int(p["said"].replace("-", ""))
near = [(p, q) for p in pts for q in pts if day(p) < day(q) and abs((datetime.date.fromisoformat(q["said"]) - datetime.date.fromisoformat(p["said"])).days) < 0.6 * 545]
assert len(pts) >= 3 and near and not any(p["above"] and q["above"] for p, q in near), [(p["said"], p["above"]) for p in pts]
assert all("expr" in l["mark"]["limit"] for l in sp["layer"] if l["mark"]["type"] == "text")
print("PASS timeline: events as known on as_of (re-resolution, replacement), series cut at as_of, bars end at the first replacement, verdict or deadline, rows grouped, settled points labelled, ids, HTML/JSON/markdown from library and CLI, the v1 data contract, an MCP Apps tool result and view, labels fit any width")
