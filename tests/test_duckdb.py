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
    con.execute(factblock.duckdb_sql().read_text())
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
        con.execute(factblock.duckdb_sql().read_text())
        for day in days:
            want = {}
            for r in sorted(factblock.scan(pq, day).to_dicts("resolutions"), key=lambda r: (r["decided_at"], r["known_at"])):
                want[r["target_id"]] = r["outcome"]
            got = dict(con.execute("SELECT target_id, outcome FROM factblock_verdicts(?, factblock_day(?))", [pq, day]).fetchall())
            assert got == want, (name, day, len(got), len(want))
# SPEC 5.3 row groups: a table past ROW_GROUP_ROWS splits into bounded groups in known_at order, the file records
# that order, and an as-of read across groups (a replacement in a later group) gives the same answer
import datetime as dt  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
from factblock.parquet import ROW_GROUP_ROWS  # noqa: E402
day0 = dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc)
at = lambda i: day0 + dt.timedelta(minutes=i)  # noqa: E731
n = ROW_GROUP_ROWS + 100
big = factblock.Bundle.__new__(factblock.Bundle)
big._load({"factblock_version": "1.0-draft.1", "namespace": "rowgroups", "declarations": {}},
          [{"id": f"n{i}", "kind": "claim", "statement": f"s{i}", "asserted_at": at(i), "valid_from": at(i), "known_at": at(i),
            "attestation": {"ledger": "process:test"}} for i in range(n)],
          [{"source_id": f"n{n - 1 - i}", "target_id": f"n{i}", "edge_type": "SUPERSEDES", "asserted_at": at(n - 1 - i),
            "valid_from": at(n - 1 - i), "known_at": at(n - 1 - i), "attestation": {"ledger": "process:test"}} for i in range(0, n, 997)], [])
with tempfile.TemporaryDirectory() as d:
    pq_dir = factblock.write_parquet(big, d)
    meta = pq.ParquetFile(pq_dir / "nodes.parquet").metadata
    sizes = [meta.row_group(g).num_rows for g in range(meta.num_row_groups)]
    assert sizes == [ROW_GROUP_ROWS, 100], sizes
    k = meta.schema.names.index("known_at")
    stats = [(meta.row_group(g).column(k).statistics.min, meta.row_group(g).column(k).statistics.max) for g in range(meta.num_row_groups)]
    assert stats[0][1] < stats[1][0], stats   # sorted by known_at: the groups do not overlap, so a reader can skip one
    assert [c.column_index for c in meta.row_group(0).sorting_columns][:2] == [k, meta.schema.names.index("id")]
    con = duckdb.connect()
    con.execute(factblock.duckdb_sql().read_text())
    for when in (at(1000), at(ROW_GROUP_ROWS + 50), at(n)):
        lib = factblock.scan(big, when)
        want = sorted(zip(lib.nodes.column("id").to_pylist(), lib.nodes.column("superseded_by").to_pylist()))
        got = con.execute("SELECT id, superseded_by FROM factblock_nodes(?, ?) ORDER BY id", [str(pq_dir), when]).fetchall()
        assert got == want, (when, len(got), len(want))
        assert con.execute("SELECT masked_nodes FROM factblock_certificate(?, ?)", [str(pq_dir), when]).fetchone()[0] == lib.certificate.get("masked", {}).get("node", 0)
# SPEC 3.1, 3.2 namespace: a real Parquet column, the same in scan and the macros on nodes and edges; a file written
# before the column existed still reads, with namespace null
TWO = ROOT / "conformance" / "bundles" / "two-namespaces"
with tempfile.TemporaryDirectory() as d:
    pq_dir = factblock.write_parquet(TWO, pathlib.Path(d) / "new")
    assert pq.read_schema(pq_dir / "nodes.parquet").field("namespace").type == "string"
    assert pq.read_table(pq_dir / "edges.parquet").column("namespace").to_pylist() == ["federalreserve.gov"]
    con = duckdb.connect()
    con.execute(factblock.duckdb_sql().read_text())
    lib = factblock.scan(pq_dir, "2024-10-31")
    for table in ("nodes", "edges"):
        key = "id" if table == "nodes" else "source_id"
        want = sorted((r[key], r.get("namespace")) for r in lib.to_dicts(table))
        got = sorted(con.execute(f"SELECT {key}, namespace FROM factblock_{table}(?, factblock_day('2024-10-31'))", [str(pq_dir)]).fetchall(), key=str)
        assert got == sorted(want, key=str), (table, got, want)
    assert "namespace" in lib.nodes.column_names and lib.nodes.num_rows == 3
    old = pathlib.Path(d) / "old"
    old.mkdir()
    (old / "factblock.json").write_text((pq_dir / "factblock.json").read_text())
    for table in ("nodes", "edges"):   # the profile as written before namespace: same file, no column
        t = pq.read_table(pq_dir / f"{table}.parquet")
        pq.write_table(t.drop_columns(["namespace"]), old / f"{table}.parquet")
    for table, key in (("nodes", "id"), ("edges", "source_id")):
        rows = con.execute(f"SELECT {key}, namespace FROM factblock_{table}(?, factblock_day('2024-10-31'))", [str(old)]).fetchall()
        assert len(rows) == (3 if table == "nodes" else 1) and all(r[1] is None for r in rows), (table, rows)
    assert all("namespace" not in r for r in factblock.scan(old, "2024-10-31").to_dicts("nodes"))
    cert = con.execute("SELECT masked_nodes, backfill_rows FROM factblock_certificate(?, factblock_day('2024-09-30'))", [str(old)]).fetchone()
    assert cert == (1, 0), cert
print("PASS duckdb macros: nodes + superseded_by + certificate match factblock.scan at three instants and under valid_at; verdicts match the library's latest visible verdict; SQL on top; bounded row groups in known_at order read the same; namespace column on nodes and edges, null in files written before it")
