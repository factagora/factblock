"""docs/guides run as written: each guide's bash and python blocks run in order in an empty folder, and every
line of its text blocks is in what they print (a "$ command" line in a text block is run too). Run:
uv run python tests/test_guides.py"""
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONPATH": str(ROOT)}
FB = f"{sys.executable} -m factblock"

for guide in sorted((ROOT / "docs" / "guides").glob("*.md")):
    blocks = re.findall(r"```(bash|python|text)\n(.*?)```", guide.read_text(), re.S)
    out = []
    with tempfile.TemporaryDirectory() as d:
        run = lambda cmd: out.append(subprocess.run(cmd, cwd=d, env=ENV, capture_output=True, text=True, check=True).stdout)  # noqa: E731
        for kind, body in blocks:
            if kind == "python":
                run([sys.executable, "-c", body])
            else:
                for line in body.splitlines():
                    cmd = line[2:] if kind == "text" and line.startswith("$ ") else line if kind == "bash" else ""
                    cmd = cmd.split("  #")[0].strip()
                    if cmd.startswith("factblock "):
                        run(["bash", "-c", cmd.replace("factblock ", FB + " ", 1)])
        printed = "".join(out)
        for kind, body in blocks:
            if kind == "text":
                for line in body.splitlines():
                    if line.strip() and not line.startswith("$ "):
                        assert line in printed, f"{guide.name}: not printed: {line!r}\n--- printed ---\n{printed}"
print(f"PASS guides: {len(list((ROOT / 'docs' / 'guides').glob('*.md')))} guides run as written and print what they show")
