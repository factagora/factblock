"""The README, run against the package on PyPI rather than this checkout: install factblock==VERSION into a fresh
venv, run the first-screen commands in an empty folder, and check that the outputs the README shows are the
outputs the package gives. Examples that read data from this repository (support-agent, cramer) get a copy of
that data, never the code. Needs uv. Exit 1 on the first mismatch.

    python scripts/check_published.py 1.0.0a13        # after a release; retries while PyPI catches up
"""
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
version = sys.argv[1]
readme = (ROOT / "README.md").read_text()


def run(cmd, cwd, **kw):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, **kw)
    if r.returncode:
        sys.exit(f"FAIL {' '.join(map(str, cmd))}\n{r.stdout}{r.stderr}")
    return r.stdout


with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    run(["uv", "venv", "-q", str(d / "venv")], d)
    py, cli = d / "venv" / "bin" / "python", d / "venv" / "bin" / "factblock"
    for attempt in range(20):   # a fresh release takes a minute or two to reach the index
        if subprocess.run(["uv", "pip", "install", "-q", "--python", str(py), "--refresh", f"factblock=={version}"], cwd=d).returncode == 0:
            break
        time.sleep(30)
    else:
        sys.exit(f"FAIL factblock=={version} is not installable from PyPI")
    work = d / "work"
    work.mkdir()
    assert run([cli, "--version"], work).split()[-1] == version

    # the first screen's four commands, as a new user types them
    run([cli, "sample", "brain/"], work)
    assert "Fed" in run([cli, "recall", "brain/", "interest rates", "--as-of", "2024-05-01"], work)
    assert "on record before it was resolved" in run([cli, "track-record", "brain/", "--as-of", "2025-01-01"], work)

    # the two examples: the package's output is what the README shows
    shutil.copytree(ROOT / "examples" / "support-agent" / "brain", work / "examples" / "support-agent" / "brain")
    shutil.copytree(ROOT / "samples" / "cramer", work / "samples" / "cramer")
    for day in ("2026-04-10", "2026-04-25"):
        out = run([py, "-I", "-c", f"import factblock; print(factblock.context('examples/support-agent/brain', 'refund window', as_of='{day}'))"], work)
        for line in out.splitlines():
            if not line.startswith("(as of"):
                assert f"# {line}" in readme, f"README lacks the context line for {day}: {line}"
    out = run([cli, "track-record", "samples/cramer", "--as-of", "2026-10-01"], work)
    for line in out.splitlines()[:4]:
        assert line in readme, f"README lacks the track-record line: {line}"

    # the block written for coding agents (tests/test_readme_agents.py runs it against the checkout)
    section = readme.split("## For coding agents", 1)[1].split("\n## ", 1)[0]
    code = section.split("```python\n", 1)[1].split("```", 1)[0]
    out = run([py, "-I", "-c", code], work)
    assert "replaced 2024-09-18 by" in out, out
print(f"PASS published: factblock {version} from PyPI runs the README's first screen, both examples and the coding-agents block as shown")
