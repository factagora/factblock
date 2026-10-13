"""The built wheel, installed in a fresh venv, carries the DuckDB macros: factblock.duckdb_sql() points at them and they
read a Parquet bundle as factblock.scan does. Needs uv. Run: uv run python tests/test_wheel.py"""
import pathlib
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHECK = """
import sys, duckdb, factblock
pq = factblock.write_parquet(factblock.Bundle(sys.argv[1]), sys.argv[2])
sql = factblock.duckdb_sql()
assert "site-packages" in str(sql), sql   # the installed copy, not the checkout's
con = duckdb.connect(); con.execute(sql.read_text())
n = con.execute("SELECT count(*) FROM factblock_nodes(?, factblock_day('2024-10-01'))", [str(pq)]).fetchone()[0]
assert n == factblock.scan(pq, "2024-10-01").nodes.num_rows > 0, n
"""

with tempfile.TemporaryDirectory() as d:
    d = pathlib.Path(d)

    def run(*a):
        r = subprocess.run(a, cwd=d, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
    run("uv", "build", "-q", "--wheel", "-o", str(d / "dist"), str(ROOT))
    run("uv", "venv", "-q", str(d / "venv"))
    py = d / "venv" / "bin" / "python"
    run("uv", "pip", "install", "-q", "--python", str(py), next((d / "dist").glob("*.whl")), "duckdb")
    run(str(py), "-I", "-c", CHECK, str(ROOT / "samples" / "rates"), str(d / "pq"))
print("PASS wheel: the installed package carries duckdb/factblock.sql at factblock.duckdb_sql(), and its macros read a Parquet bundle as scan does")
