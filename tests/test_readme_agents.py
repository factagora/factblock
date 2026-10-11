"""The README's "For coding agents" block runs as written: its factblock commands, then its Python.
Run: uv run python tests/test_readme_agents.py"""
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONPATH": str(ROOT)}
section = (ROOT / "README.md").read_text().split("## For coding agents", 1)[1].split("\n## ", 1)[0]
setup = re.findall(r"```bash\n(.*?)```", section, re.S)[0]
code = re.findall(r"```python\n(.*?)```", section, re.S)[0]
with tempfile.TemporaryDirectory() as d:
    for line in setup.splitlines():
        if line.startswith("factblock "):
            subprocess.run([sys.executable, "-m", "factblock", *line.split("#")[0].split()[1:]], cwd=d, check=True, capture_output=True, env=ENV)
    out = subprocess.run([sys.executable, "-c", code], cwd=d, check=True, capture_output=True, text=True, env=ENV).stdout
assert "replaced 2026-07-01 by" in out and out.strip().endswith("-> The IRS business standard mileage rate is 76 cents per mile."), out
print("PASS README for-coding-agents block runs as written")
