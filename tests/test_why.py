"""The one check that fails if `why` breaks: the chain behind c3 grows as the instant moves,
roles name the right end of each edge, and a block not yet known gives a reason, not a chain.
Run: uv run python tests/test_why.py"""
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import factblock  # noqa: E402

RATES = pathlib.Path(__file__).resolve().parents[1] / "samples" / "rates"
by_id = lambda r: {x["id"]: x for x in r["chain"]}  # noqa: E731

aug = by_id(factblock.why(RATES, "c3", "2024-08-01"))
assert set(aug) == {"c3", "c2", "c1"}, aug
assert aug["c3"]["role"] == "subject" and aug["c3"]["depth"] == 0 and aug["c3"]["via"] is None
assert aug["c2"]["role"] == "cause" and aug["c2"]["depth"] == 1 and aug["c2"]["via"]["edge_type"] == "CAUSES"
assert aug["c1"]["role"] == "cause" and aug["c1"]["depth"] == 2 and aug["c1"]["path"] == ["c3", "c2", "c1"]

octo = factblock.why(RATES, "c3", "2024-10-01")
assert set(by_id(octo)) == {"c3", "c2", "c1", "c4"}
assert by_id(octo)["c4"]["role"] == "successor" and by_id(octo)["c4"]["depth"] == 3
assert [r["id"] for r in octo["chain"]] == ["c1", "c2", "c3", "c4"]           # ordered by asserted_at
assert set(by_id(factblock.why(RATES, "c3", "2024-10-01", depth=1))) == {"c3", "c2"}
assert by_id(factblock.why(RATES, "c1", "2024-10-01", depth=1))["c2"]["role"] == "effect"
assert by_id(factblock.why(RATES, "c1", "2024-10-01", depth=1))["c4"]["role"] == "successor"
assert by_id(factblock.why(RATES, "c4", "2024-10-01", depth=1))["c1"]["role"] == "predecessor"

may = factblock.why(RATES, "c3", "2024-05-01")
assert may["chain"] == [] and may["reason"] == "not_yet" and may["certificate"]["masked"]["node"] == 4, may
assert factblock.why(RATES, "nope", "2024-05-01")["reason"] == "absent"

out = subprocess.run([sys.executable, "-m", "factblock", "why", str(RATES), "c3", "--as-of", "2024-08-01"], capture_output=True, text=True, check=True).stdout
assert "subject: c3" in out and "        cause (CAUSES): c1" in out, out
out = subprocess.run([sys.executable, "-m", "factblock", "why", str(RATES), "c3", "--as-of", "2024-08-01", "--json"], capture_output=True, text=True, check=True).stdout
assert '"role": "cause"' in out and '"c1"' in out, out
print("PASS why: chain at three instants, roles both ends, depth, not_yet/absent, CLI")
