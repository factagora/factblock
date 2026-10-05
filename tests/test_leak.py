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

p = subprocess.run([sys.executable, "-m", "factblock", "leak", str(RATES), str(QS)], capture_output=True, text=True)
assert p.returncode == 1 and "1/3 questions leak" in p.stdout and "c3 known 2024-07-01" in p.stdout, p.stdout
print("PASS leak: 1 of 3 questions, block and known_at named, missing id, not_in_force via valid_at, CLI exit 1")
