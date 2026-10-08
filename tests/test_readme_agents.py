"""The README's "For coding agents" block runs as written. Run: uv run python tests/test_readme_agents.py"""
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
section = (ROOT / "README.md").read_text().split("## For coding agents", 1)[1].split("\n## ", 1)[0]
code = re.findall(r"```python\n(.*?)```", section, re.S)[0]
with tempfile.TemporaryDirectory() as d:
    subprocess.run([sys.executable, "-m", "factblock", "sample", "brain/"], cwd=d, check=True, capture_output=True,
                   env={**os.environ, "PYTHONPATH": str(ROOT)})
    out = subprocess.run([sys.executable, "-c", code], cwd=d, check=True, capture_output=True, text=True,
                         env={**os.environ, "PYTHONPATH": str(ROOT)}).stdout
assert "replaced 2024-09-18 by" in out and out.strip().endswith("The Fed cuts interest rates true"), out
print("PASS README for-coding-agents block runs as written")
