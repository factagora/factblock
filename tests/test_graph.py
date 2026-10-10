"""The one check that fails if graph breaks: the walk is read as of as_of (a link or verdict learned later is not
drawn), a call past its horizon is still drawn unless valid_at asks for what was in force, the rows use the
renderer field names, what a statement rests on sits above it and what came of it below, and the chart saves and
returns an MCP tool result.
Run: uv run python tests/test_graph.py"""
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import factblock  # noqa: E402

CRAMER = ROOT / "samples" / "cramer"
BULLS = "ba4c1a04d78f5848"   # 2025-03-25 "bulls hold the advantage", due 2025-04-02, judged wrong, replaced 2025-04-22

g = factblock.graph(CRAMER, BULLS, "2025-06-30")
by = {n["id"]: n for n in g.nodes}
assert by[BULLS]["root"] and by[BULLS]["status"] == "wrong" and by[BULLS]["resolution"] == "wrong", by[BULLS]
succ = next(n for n in g.nodes if n["role"] == "successor")
assert succ["row"] > by[BULLS]["row"] and all(n["row"] < by[BULLS]["row"] for n in g.nodes if n["role"] in ("support", "cause"))
assert {e["label"] for e in g.edges} >= {"SUPERSEDES"} and all({"id", "from", "to", "label"} <= set(e) for e in g.edges)
assert all({"id", "label", "type", "when", "resolution"} <= set(n) for n in g.nodes)

# as of 2025-04-10 the replacement (said 2025-04-22) is not known, and the verdict of 2025-04-03 is
early = factblock.graph(CRAMER, BULLS, "2025-04-10")
assert not any(n["role"] == "successor" for n in early.nodes) and next(n for n in early.nodes if n["root"])["status"] == "wrong"
# as of 2025-04-02 it is still open: the verdict is not known yet
assert next(n for n in factblock.graph(CRAMER, BULLS, "2025-04-02").nodes if n["root"])["status"] == "open"
# past its horizon it is drawn; asked for what was in force on 2025-06-30, it is not
try:
    factblock.graph(CRAMER, BULLS, "2025-06-30", valid_at="2025-06-30")
    raise AssertionError("a call past its horizon was drawn as in force")
except ValueError as e:
    assert "not in force" in str(e), e
try:
    factblock.graph(CRAMER, BULLS, "2025-03-01")
    raise AssertionError("a block said later was drawn")
except ValueError as e:
    assert "not known yet" in str(e), e

d = g.to_dict()
assert d["schema"] == "factblock.graph/v1" and d["root"] == BULLS and json.dumps(d, default=str)
r = g.to_mcp()
assert r["structuredContent"]["schema"] == "factblock.graph/v1" and "layer" in r["_meta"]["factblock/vega-lite"] and BULLS in r["content"][0]["text"]
deep = factblock.graph(CRAMER, "fdc79a63b9b44a7f", "2025-06-30", depth=2)
assert max(n["depth"] for n in deep.nodes) == 2 and len(deep.nodes) > len(factblock.graph(CRAMER, "fdc79a63b9b44a7f", "2025-06-30").nodes)

with tempfile.TemporaryDirectory() as tmp:
    out = pathlib.Path(tmp) / "g.html"
    p = subprocess.run([sys.executable, "-m", "factblock", "graph", str(CRAMER), BULLS, "--as-of", "2025-06-30", "-o", str(out)], capture_output=True, text=True)
    assert p.returncode == 0 and "vegaEmbed" in out.read_text(), p.stdout + p.stderr
print("PASS graph: walk as of as_of (later links and verdicts hidden), calls past their horizon drawn unless valid_at, renderer field names, rests-on above and came-of-it below, depth, JSON/MCP/HTML from library and CLI")
