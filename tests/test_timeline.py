"""The one check that fails if timeline breaks: lanes carry said / learned / replaced / verdict events as known on
as_of (a re-resolution shows as a second verdict, a later replacement is not drawn early), a series is cut at
as_of, deadlines become spans, and the chart saves as HTML and JSON from the library and the CLI.
Run: uv run python tests/test_timeline.py"""
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import factblock  # noqa: E402

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
assert s.spec()["vconcat"][0]["layer"][0]["encoding"]["y"]["title"] == "Fed funds rate (%)"
try:
    t.with_series([("2030-01-01", 1.0)]); raise AssertionError("a series entirely after as_of must be refused")
except ValueError as e:
    assert "on or before as_of" in str(e)

promises = ROOT / "examples" / "promises" / "brain"
assert {c["id"]: c["status"] for c in factblock.timeline(promises, "2026-04-01").claims} == {"p1": "open", "p2": "open", "p3": "open"}
late = factblock.timeline(promises, "2026-05-10")
assert {c["id"]: (c["status"], c["due"]) for c in late.claims} == {"p1": ("right", "2026-04-30"), "p2": ("wrong", "2026-03-31"), "p3": ("open", "2026-06-30")}
assert late.spec()["layer"][0]["data"]["values"][0]["t2"]   # deadlines are drawn as spans

assert [c["id"] for c in factblock.timeline(RATES, "2025-01-01", ids=["c4", "c1"]).claims] == ["c1", "c4"]
try:
    factblock.timeline(RATES, "2024-06-01", ids=["c4"]); raise AssertionError("c4 was not known yet")
except ValueError as e:
    assert "c4" in str(e)

m = t._repr_mimebundle_()
assert "application/vnd.vegalite.v5+json" in m and m["application/vnd.vegalite.v5+json"]["layer"][2]["encoding"]["href"] == {"field": "source"}
with tempfile.TemporaryDirectory() as d:
    d = pathlib.Path(d)
    s.save(d / "t.html"); s.save(d / "t.json"); s.save(d / "t.vl.json")
    assert "vegaEmbed" in (d / "t.html").read_text() and json.loads((d / "t.json").read_text())["series"][0] == {"t": "2024-01-01", "value": 5.33}
    p = subprocess.run([sys.executable, "-m", "factblock", "timeline", str(RATES), "--as-of", "2025-01-01", "-q", "interest rates",
                        "--series", str(FFR), "-o", str(d / "c.html")], capture_output=True, text=True)
    assert p.returncode == 0 and (d / "c.html").exists() and "3 statements" in p.stdout, p.stdout + p.stderr
print("PASS timeline: events as known on as_of (re-resolution, replacement), series cut at as_of, deadlines as spans, ids, HTML/JSON from library and CLI")
