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
    # with valid_at the two certificates still agree (SPEC 4.2): masked is learned-later only,
    # not_in_force is known but not in force at valid_at
    for day, at in (("2024-10-01", "2024-06-01T00:00:00+00:00"), ("2024-10-01", "2024-03-25T00:00:00+00:00"), ("2024-08-01", "2024-12-01T00:00:00+00:00")):
        lib = factblock.scan(pq, day, valid_at=at)
        cert = con.execute("SELECT masked_nodes, masked_edges, not_in_force_nodes, not_in_force_edges FROM factblock_certificate(?, factblock_day(?), valid_at := CAST(? AS TIMESTAMPTZ))", [pq, day, at]).fetchone()
        m, f = lib.certificate.get("masked", {}), lib.certificate.get("not_in_force", {})
        assert cert == (m.get("node", 0), m.get("edge", 0), f.get("node", 0), f.get("edge", 0)), (day, at, cert, lib.certificate)
    # plain SQL on top of the macro, the thing the pack exists for
    n = con.execute("SELECT count(*) FROM factblock_nodes(?, factblock_day('2024-10-01')) WHERE kind = 'claim' AND superseded_by IS NOT NULL", [pq]).fetchone()[0]
    assert n == 1
# verdicts: the latest visible one per block, as recall() picks it, on rates (a re-resolution) and cramer (779 settled calls)
for name, days in (("rates", ("2024-06-01", "2024-12-31", "2025-06-01")), ("cramer", ("2024-12-01", "2025-06-01", "2026-09-10"))):
    with tempfile.TemporaryDirectory() as d:
        pq = str(factblock.write_parquet(ROOT / "samples" / name, d))
        con = duckdb.connect()
        con.execute((ROOT / "duckdb" / "factblock.sql").read_text())
        for day in days:
            want = {}
            for r in sorted(factblock.scan(pq, day).to_dicts("resolutions"), key=lambda r: (r["decided_at"], r["known_at"])):
                want[r["target_id"]] = r["outcome"]
            got = dict(con.execute("SELECT target_id, outcome FROM factblock_verdicts(?, factblock_day(?))", [pq, day]).fetchall())
            assert got == want, (name, day, len(got), len(want))
print("PASS duckdb macros: nodes + superseded_by + certificate match factblock.scan at three instants and under valid_at; verdicts match the library's latest visible verdict; SQL on top")
