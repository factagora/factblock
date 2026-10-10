"""`factblock demo` runs every scene on both samples and puts the real numbers on screen.
Run: uv run python tests/test_demo.py (needs the dev group or the demo extra: Rich)."""
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
env = {**os.environ, "FACTBLOCK_DEMO_FAST": "1", "PYTHONPATH": str(ROOT), "COLUMNS": "100"}


def demo(*args):
    return subprocess.run([sys.executable, "-m", "factblock", "demo", *args], cwd=ROOT, env=env, check=True, capture_output=True, text=True).stdout


out = demo("timeline", "samples/cramer", "--as-of", "2024-09-30", "2026-09-10")
assert "1,958" in out and "779" in out, out                       # scan as of 2026-09-10: blocks, verdicts
out = demo("why", "samples/cramer", "f8c739a204944e7f", "--as-of", "2026-09-10")
assert "successor" in out and "7 blocks in the chain" in out, out
out = demo("replaced", "samples/rates", "c1", "--as-of", "2024-10-01", "2024-08-01")
assert "c1 · current" in out and "c4 · not known yet" in out, out  # the last date drawn: before c4 was known
out = demo("verdict", "samples/cramer", "66027d5985bf9605")
assert "CAME TRUE" in out and "NVDA +23.3%" in out, out            # resolution value.return 0.2328
out = demo("verdict", "samples/rates", "c1")
assert "TRUE" in out, out
out = demo("leak", "bench/streamingqa/results.json")
assert "79.7%" in out and "797 of 1,000" in out, out
assert "pip install --pre factblock" in demo("end") and "Agent memory with a track record." in demo("title")
print("PASS demo: every scene renders on samples/cramer, samples/rates and the StreamingQA results with their real numbers")
