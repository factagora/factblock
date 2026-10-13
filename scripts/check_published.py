"""The README, run against the package on PyPI rather than this checkout: install factblock==VERSION into a fresh
venv, run the first-screen commands in an empty folder, and check that the outputs the README shows are the
outputs the package gives. The second example reads data from this repository (cramer) and gets a copy of that
data, never the code. Needs uv. Exit 1 on the first mismatch.

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

    # the first screen's commands, as a new user types them, then the first example on the folder they made
    run([cli, "sample", "--policies", "irs/"], work)
    run([cli, "import", "irs/mileage.csv", "--backfill", "-o", "brain/"], work)
    run([cli, "import", "irs/mileage-2026-07.csv", "--backfill", "-o", "brain/"], work)
    for as_of, n, rate in (("2026-07-10", "1", "72.5 cents"), ("2026-07-20", "2", "76 cents")):
        out = run([cli, "recall", "brain/", "mileage rate", "--as-of", as_of, "--limit", n], work)
        assert rate in out.splitlines()[0], out
        for line in out.splitlines():
            assert line in readme, f"README lacks the recall line for {as_of}: {line}"
    assert "7 statements" in run([cli, "timeline", "brain/", "--as-of", "2026-10-10", "-o", "mileage.html"], work)
    for as_of, n in (("2026-07-10", 1), ("2026-07-20", 2)):
        out = run([py, "-I", "-c", f"import factblock; print(factblock.context('brain/', 'mileage rate', as_of='{as_of}', valid_at='2026-07-05', limit={n}))"], work)
        for line in out.splitlines():
            if not line.startswith("(as of"):
                assert f"# {line}" in readme, f"README lacks the context line for {as_of}: {line}"
    shutil.copytree(ROOT / "samples" / "cramer", work / "samples" / "cramer")   # the second example reads the repository's data
    out = run([cli, "track-record", "samples/cramer", "--as-of", "2026-10-01"], work)
    for line in out.splitlines()[:4]:
        assert line in readme, f"README lacks the track-record line: {line}"

    # DuckDB reads the same folder through the macros the wheel carries
    run(["uv", "pip", "install", "-q", "--python", str(py), "duckdb"], d)
    run([cli, "to-parquet", "brain/", "brain-pq/"], work)
    run([py, "-I", "-c", "import duckdb, factblock; con = duckdb.connect(); con.execute(factblock.duckdb_sql().read_text()); "
         "n = con.execute(\"SELECT count(*) FROM factblock_nodes('brain-pq', factblock_day('2026-07-20'))\").fetchone()[0]; "
         "assert n == factblock.scan('brain-pq', '2026-07-20').nodes.num_rows > 0, n"], work)

    # the block written for coding agents (tests/test_readme_agents.py runs it against the checkout)
    section = readme.split("## For coding agents", 1)[1].split("\n## ", 1)[0]
    setup = section.split("```bash\n", 1)[1].split("```", 1)[0]
    code = section.split("```python\n", 1)[1].split("```", 1)[0]
    (work / "agents").mkdir()
    for line in setup.splitlines():
        if line.startswith("factblock "):
            run([cli, *line.split("#")[0].split()[1:]], work / "agents")
    out = run([py, "-I", "-c", code], work / "agents")
    assert "replaced by (announced 2026-07-13, in force from 2026-07-01)" in out, out
print(f"PASS published: factblock {version} from PyPI runs the README's first screen, both examples, the DuckDB macros and the coding-agents block as shown")
