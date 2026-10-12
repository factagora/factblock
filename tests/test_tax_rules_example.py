"""examples/tax-rules: twelve dated tax questions over public U.S. tax law that changed. Read as of the day
asked, for the day the question is about, with only the rows that apply to the client, the most specific
row in force answers all twelve without a model. Firm advice whose basis was replaced is flagged only once
the replacement is known. Run: uv run python tests/test_tax_rules_example.py"""
import pathlib
import runpy

ROOT = pathlib.Path(__file__).resolve().parents[1]
ex = runpy.run_path(str(ROOT / "examples" / "tax-rules" / "run.py"))

got = {q["id"]: ex["factblock_read"](q)["value"] for q in ex["QUESTIONS"]}
want = {q["id"]: q["answer"] for q in ex["QUESTIONS"]}
assert got == want, {k: (got[k], want[k]) for k in want if got[k] != want[k]}

assert ex["applies"]({"applies_if": "acquired_after=2025-01-19"}, {"acquired": "2025-02-10"})
assert not ex["applies"]({"applies_if": "acquired_after=2025-01-19"}, {"acquired": "2024-12-05"})
assert not ex["applies"]({"applies_if": "county=Los Angeles"}, {})                  # a fact the client lacks
assert ex["applies"]({"applies_if": ""}, {"county": "Orange"})

assert ex["renotify"]("2025-06-01") == []                                          # the law had not changed yet
assert [x.split(" ")[0] for x in ex["renotify"]("2026-10-12")] == ["memo-client-a"]
# a firm's own files repeat old answers; declared as resting on a rule (based_on), they must not crowd it out
ex["ROWS"].extend(ex["restatements"]())
ex["_views"].clear()
got = {q["id"]: ex["factblock_read"](q)["value"] for q in ex["QUESTIONS"]}
assert got == want, {k: (got[k], want[k]) for k in want if got[k] != want[k]}

flagged = {x.split(" ")[0] for x in ex["renotify"]("2026-10-12")}
assert {f"boi-rule-mail-{n}" for n in range(8)} <= flagged, flagged                # replaced after they were sent, too
assert not any(x.startswith("bonus-2025-mail") for x in flagged), flagged           # no client facts: the 100% rule does not apply

print("PASS tax-rules example: 12/12 without a model, also with 16 stale restatements added; advice flagged only after its basis was replaced")
