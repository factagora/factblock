"""The DuckDB macro pack answers exactly like factblock.scan(): same rows, same
superseded_by, same masked counts, at three instants. Run: uv run python tests/test_duckdb.py"""
import pathlib
import sys
import tempfile

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import factblock  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as d:
    pq = str(factblock.write_parquet(ROOT / "samples" / "rates", d))
    con = duckdb.connect()
    con.execute((ROOT / "duckdb" / "factblock.sql").read_text())
    for day in ("2024-05-01", "2024-08-01", "2024-10-01"):
        lib = factblock.scan(pq, day)
        rows = con.execute("SELECT id, superseded_by FROM factblock_nodes(?, factblock_day(?)) ORDER BY id", [pq, day]).fetchall()
        want = sorted(zip(lib.nodes.column("id").to_pylist(), lib.nodes.column("superseded_by").to_pylist()))
        assert rows == want, (day, rows, want)
        cert = con.execute("SELECT masked_nodes, masked_edges, backfill_batches, backfill_rows FROM factblock_certificate(?, factblock_day(?))", [pq, day]).fetchone()
        m = lib.certificate.get("masked", {}); b = lib.certificate.get("backfill", {})
        assert cert == (m.get("node", 0), m.get("edge", 0), b.get("batches", 0), b.get("rows", 0)), (day, cert, lib.certificate)
    # valid_at selects content, as in the library
    rows = con.execute("SELECT id FROM factblock_nodes(?, factblock_day('2024-10-01'), valid_at := TIMESTAMPTZ '2024-06-01') ORDER BY id", [pq]).fetchall()
    assert [r[0] for r in rows] == ["c1", "c2"], rows
    # plain SQL on top of the macro, the thing the pack exists for
    n = con.execute("SELECT count(*) FROM factblock_nodes(?, factblock_day('2024-10-01')) WHERE kind = 'claim' AND superseded_by IS NOT NULL", [pq]).fetchone()[0]
    assert n == 1
print("PASS duckdb macros: nodes + superseded_by + certificate match factblock.scan at three instants; valid_at; SQL on top")
