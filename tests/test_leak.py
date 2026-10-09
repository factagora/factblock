"""The one check that fails if `leak` breaks: a question whose evidence was learned after it was
asked is flagged with the block and its known_at, a clean one is not, an unknown id is missing,
and the CLI exits non-zero on a leak. Run: uv run python tests/test_leak.py"""
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import factblock  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
RATES, QS = ROOT / "samples" / "rates", ROOT / "samples" / "rates-questions.jsonl"

r = factblock.leak(RATES, QS)
assert (r["questions"], r["leaked_questions"], r["leaked_blocks"], r["missing_blocks"]) == (3, 1, 1, 0), r
q = {x["id"]: x for x in r["per_question"]}
assert q["q1"]["leaked"] == [] and q["q3"]["leaked"] == []
assert q["q2"]["leaked"][0]["id"] == "c3" and q["q2"]["leaked"][0]["known_at"].startswith("2024-07-01") and q["q2"]["leaked"][0]["reason"] == "known_later"

r2 = factblock.leak(RATES, [{"asked_at": "2024-10-01", "evidence": ["c4", "zzz"]},
                            {"asked_at": "2024-10-01", "valid_at": "2024-06-01", "evidence": ["c4"]}])   # c4 known, but not in force in June
assert r2["per_question"][0]["missing"] == ["zzz"] and r2["per_question"][0]["leaked"] == [] and r2["per_question"][0]["id"] == 0
assert r2["per_question"][1]["leaked"][0]["reason"] == "not_in_force"
assert factblock.leak(RATES, [])["leak_rate"] == 0.0

# a question the check cannot read must fail loudly, not pass as leak-free
for bad in ({"asked_at": "2024-10-01", "blocks": ["c4"]}, {"evidence": ["c4"]}, {"asked_at": "2024-10-01", "evidence": "c4"}):
    try:
        factblock.leak(RATES, [bad]); raise AssertionError(bad)
    except ValueError as e:
        assert "asked_at and evidence" in str(e)
bad = ROOT / "tests" / "_leak_bad.jsonl"
bad.write_text('{"id": "x", "asked_at": "2024-10-01", "evidence": ["zzz"]}\n')
try:
    p = subprocess.run([sys.executable, "-m", "factblock", "leak", str(RATES), str(bad)], capture_output=True, text=True)
    assert p.returncode == 1 and "1 evidence ids not in the bundle" in p.stdout, p.stdout
    bad.write_text('{"id": "x", "asked_at": "2024-10-01", "blocks": ["c4"]}\n')
    p = subprocess.run([sys.executable, "-m", "factblock", "leak", str(RATES), str(bad)], capture_output=True, text=True)
    assert p.returncode != 0 and "needs asked_at and evidence" in p.stderr and "Traceback" not in p.stderr, p.stderr
finally:
    bad.unlink()
# a date-only asked_at is the start of that day: news ingested at 02:00 leaks into a question dated that day
import tempfile  # noqa: E402
with tempfile.TemporaryDirectory() as d:
    factblock.write_bundle({"nodes": [{"id": "n2", "kind": "claim", "statement": "guidance cut", "asserted_at": "2025-03-20T21:00:00Z",
                                       "known_at": "2025-03-21T02:00:00Z"}]}, d)
    assert factblock.leak(d, [{"asked_at": "2025-03-21", "evidence": ["n2"]}])["leaked_questions"] == 1
    assert factblock.leak(d, [{"asked_at": "2025-03-21T03:00:00Z", "evidence": ["n2"]}])["leaked_questions"] == 0
    qf = pathlib.Path(d) / "q.jsonl"
    qf.write_text('{"id": "q2", "asked_at": "2025-03-21T00:00:00Z", "evidence": ["n2"]}\n')
    out = subprocess.run([sys.executable, "-m", "factblock", "leak", d, str(qf)], capture_output=True, text=True).stdout
    assert "q2: asked 2025-03-21 00:00, n2 known 2025-03-21 02:00" in out, out   # same day: the minute is shown
p = subprocess.run([sys.executable, "-m", "factblock", "leak", str(RATES), str(QS), "--json"], capture_output=True, text=True)
assert p.returncode == 1 and '"leaked_questions": 1' in p.stdout, p.stdout

p = subprocess.run([sys.executable, "-m", "factblock", "leak", str(RATES), str(QS)], capture_output=True, text=True)
assert p.returncode == 1 and "1/3 questions leak" in p.stdout and "c3 known 2024-07-01" in p.stdout, p.stdout
print("PASS leak: 1 of 3 questions, block and known_at named, missing id, not_in_force via valid_at, date-only asked_at = start of day, same-day minutes shown, malformed questions refused, CLI exit 1 on leak or unknown id, --json")
