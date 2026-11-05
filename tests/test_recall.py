"""The one check that fails if recall breaks: ranked by hits, masked by as_of, kinds filtered,
and context() is prompt-ready lines. Run: uv run python tests/test_recall.py"""
import pathlib
import subprocess
import sys
import tempfile

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
assert ctx.startswith("- 2024-03-20: The Fed raises interest rates") and ctx.endswith("(as of 2024-05-01)"), ctx
# what happened to a block since, as far as it was known then: replaced (SUPERSEDES row), verdict (resolutions row)
c1 = lambda t: next(i for i in factblock.recall(RATES, "interest rates", t)["items"] if i["id"] == "c1")  # noqa: E731
assert "superseded_by" not in c1("2024-05-01") and "verdict" not in c1("2024-05-01")   # verdict known 05-02, cut 09
assert c1("2024-10-01")["superseded_by"]["id"] == "c4" and c1("2024-10-01")["verdict"]["outcome"] == "true"
assert c1("2025-01-01")["verdict"]["outcome"] == "false"                                # re-resolved 2024-12-01
assert c1("2024-10-01")["known_at"].date().isoformat() == "2024-04-15"
ctx = factblock.context(RATES, "interest rates", "2024-10-01")
assert "- 2024-03-20: The Fed raises interest rates (learned 2024-04-15)" in ctx, ctx
assert "  replaced 2024-09-18 by: The Fed cuts interest rates" in ctx and "  verdict: true (decided 2024-05-01" in ctx, ctx
assert "verdict" not in factblock.context(RATES, "interest rates", "2024-05-01")
out = subprocess.run([sys.executable, "-m", "factblock", "recall", str(RATES), "rates", "--as-of", "2024-10-01"], capture_output=True, text=True, check=True).stdout
assert out.startswith("c4") and "of 3 matching" in out, out
# fact_key: only blocks carrying that key, whatever words they share with the query
fk = factblock.recall(RATES, "", "2024-10-01", fact_key="belief:tsla:direction")
assert sorted(ids(fk)) == ["t1", "t2"], ids(fk)
assert sorted(ids(factblock.recall(RATES, "", "2024-10-01", fact_key=["belief:tsla:direction", "belief:fed:direction"]))) == ["c1", "c4", "t1", "t2"]
assert "TSLA" not in factblock.context(RATES, "goes", "2024-10-01", fact_key="belief:fed:direction")
out = subprocess.run([sys.executable, "-m", "factblock", "recall", str(RATES), "", "--as-of", "2024-10-01", "--fact-key", "belief:tsla:direction"], capture_output=True, text=True, check=True).stdout
assert "2 of 2 matching" in out, out

# a note resting on a rule (based_on, a DERIVED_FROM edge) says when the rule was replaced, as known at as_of; one hop
rows = [{"id": "r1", "said_at": "2025-01-01", "text": "The rate is 40%."},
        {"id": "r2", "said_at": "2025-07-04", "effective_from": "2025-01-20", "text": "The rate is 100%.", "replaces": "r1"},
        {"id": "m1", "said_at": "2025-03-15", "text": "Your equipment gets the 40% rate.", "based_on": "r1"},
        {"id": "m2", "said_at": "2025-03-16", "text": "As the note said, 40% rate.", "based_on": "m1"}]
with tempfile.TemporaryDirectory() as d:
    factblock.write_bundle(factblock.from_records(rows, backfill=True), d)
    m = lambda t: next(i for i in factblock.recall(d, "rate", t, valid_at="2025-03-20")["items"] if i["id"] == "m1")  # noqa: E731
    assert "basis_replaced" not in m("2025-06-01")                                      # the new law was not known yet
    br = m("2026-01-01")["basis_replaced"]
    assert [(x["id"], x["by"], x["since"].date().isoformat()) for x in br] == [("r1", "r2", "2025-01-20")], br
    ctx = factblock.context(d, "rate", "2026-01-01", valid_at="2025-03-20")
    assert "  rests on r1, replaced by (announced 2025-07-04, in force from 2025-01-20): The rate is 100%." in ctx, ctx
    assert ctx.count("rests on") == 1, ctx                                              # m2 rests on m1, not replaced: no mark
    out = subprocess.run([sys.executable, "-m", "factblock", "recall", d, "rate", "--as-of", "2026-01-01", "--valid-at", "2025-03-20"],
                         capture_output=True, text=True, check=True).stdout
    assert "rests on r1, replaced by r2 (announced 2025-07-04, in force from 2025-01-20): The rate is 100%." in out, out   # CLI says it as context does
# a replacement for some cases only (SPEC 4.3): the old rule stays live, marked with who the new one is for
COND = pathlib.Path(__file__).resolve().parents[1] / "conformance" / "bundles" / "conditional"
i = next(i for i in factblock.recall(COND, "bonus depreciation", "2025-07-10")["items"] if i["id"] == "bonus-40")
assert "superseded_by" not in i and [(x["id"], x["since"].date().isoformat()) for x in i["superseded_for"]] == [("bonus-100", "2025-01-20")], i
ctx = factblock.context(COND, "bonus depreciation", "2025-07-10")
assert "  replaced for acquired after 2025-01-19 by (announced 2025-07-04, in force from 2025-01-20): Bonus depreciation is 100%" in ctx, ctx
ctx = factblock.context(COND, "elect", "2025-07-10")   # a total replacement keeps its line
out = subprocess.run([sys.executable, "-m", "factblock", "recall", str(COND), "bonus", "--as-of", "2025-07-10"], capture_output=True, text=True, check=True).stdout
assert "for acquired after 2025-01-19, replaced by bonus-100 (announced 2025-07-04, in force from 2025-01-20)" in out, out
assert "  replaced 2024-09-01 by: Partnerships and S corporations elect by April 15." in ctx and "replaced for" not in ctx, ctx
# a malformed applies_if does not break a read: its replacement is listed for "some cases", never total
MAL = COND.parent / "malformed-conditions"
ctx = factblock.context(MAL, "", "2026-03-01", limit=20)
assert ctx.count("for some cases by:") == 5 and ctx.count("replaced 2026-02-01 by:") == 3, ctx
print("PASS recall: ranked by hits and recency, masked by as_of, limit, context lines, replaced/verdict/learned as known at as_of, CLI, fact_key, basis replaced, replaced for some cases, malformed applies_if")
