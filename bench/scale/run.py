"""Scale baseline for the Parquet profile (SPEC 5.3): DuckDB as-of reads on one row group per table (the
writer before 1.0.0a17) against bounded row groups (write_parquet now), on a synthetic bundle, with the
answers checked against factblock.scan. Synthetic rows only; nothing is downloaded or committed.

    uv run python bench/scale/run.py 100000 [workdir]

Prints a JSON result. Rows: N claims said over 2000..2025, each learned at the end of its day (one backfill
batch per day), 3% replaced by a later claim (SUPERSEDES), 5% restated (RESTATES)."""
import json
import os
import random
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import factblock  # noqa: E402
from factblock.parquet import to_table  # noqa: E402

WORDS = "rate price index policy rule filing notice report forecast guidance budget tariff wage supply demand yield".split()
AS_OF = ("2010-06-30", "2024-01-31", "2025-12-31")   # early history, mid, everything


def synth(n: int, seed: int = 20261013) -> dict:
    rnd = random.Random(seed)
    t0, span = datetime(2000, 1, 1, tzinfo=timezone.utc), 26 * 365 * 86400
    said = sorted(t0 + timedelta(seconds=rnd.randrange(span)) for _ in range(n))
    nodes, edges = [], []
    for i, a in enumerate(said):
        learned = a.replace(hour=23, minute=59, second=59)   # the end of the day it was said
        nodes.append({"id": f"c{i}", "kind": "claim", "statement": " ".join(rnd.choices(WORDS, k=24)),
                      "payload": {"source": {"id": f"doc-{i // 7}"}}, "asserted_at": a, "known_at": learned})
    for i in rnd.sample(range(n - 1), n * 8 // 100):
        j = rnd.randrange(i + 1, n)   # a later claim
        typ = "SUPERSEDES" if len(edges) < n * 3 // 100 else "RESTATES"
        a = nodes[j]["asserted_at"]
        edges.append({"source_id": f"c{j}", "target_id": f"c{i}", "edge_type": typ, "asserted_at": a, "known_at": nodes[j]["known_at"]})
    return {"nodes": nodes, "edges": edges}


def best(con, sql, args, k=3):
    out = None
    for _ in range(k):
        t = time.perf_counter(); rows = con.execute(sql, args).fetchall(); s = time.perf_counter() - t
        out = (min(out[0], s), rows) if out else (s, rows)
    return out


def main(n: int, work: Path) -> dict:
    t = time.perf_counter()
    src = factblock.write_bundle(synth(n), work / "jsonl", captured_at="2026-10-13T00:00:00Z", reason="synthetic")
    b = factblock.Bundle(src)
    res = {"n_nodes": n, "n_edges": len(b.edges), "batches": len(b.backfills), "cpus": os.cpu_count(),
           "duckdb": duckdb.__version__, "write_jsonl_s": round(time.perf_counter() - t, 2), "layouts": {}}
    one = work / "one-row-group"; one.mkdir()
    (one / "factblock.json").write_text(json.dumps({**b.manifest, "tables": {"nodes": "nodes.parquet", "edges": "edges.parquet"}}, default=str))
    for name, rows in (("nodes", b.nodes), ("edges", b.edges)):
        pq.write_table(to_table(rows, name), one / f"{name}.parquet", compression="zstd")   # the writer before 1.0.0a17
    t = time.perf_counter(); bounded = factblock.write_parquet(b, work / "bounded")
    res["write_parquet_s"] = round(time.perf_counter() - t, 2)
    want = {}
    for day in AS_OF:
        s = factblock.scan(b, day)
        want[day] = (s.nodes.num_rows, sum(x is not None for x in s.nodes.column("superseded_by").to_pylist()), s.certificate.get("masked", {}).get("node", 0))
    con = duckdb.connect()
    con.execute(factblock.duckdb_sql().read_text())
    for label, d in (("one_row_group", one), ("bounded", bounded)):
        meta = pq.ParquetFile(d / "nodes.parquet").metadata
        lay = {"row_groups": meta.num_row_groups, "nodes_mb": round((d / "nodes.parquet").stat().st_size / 2**20, 1), "as_of": {}}
        for day in AS_OF:
            s_n, (got,) = best(con, "SELECT count(*), count(superseded_by) FROM factblock_nodes(?, factblock_day(?))", [str(d), day])
            s_c, (cert,) = best(con, "SELECT masked_nodes FROM factblock_certificate(?, factblock_day(?))", [str(d), day])
            assert (*got, cert[0]) == want[day], (label, day, got, cert, want[day])   # same answer as scan
            lay["as_of"][day] = {"nodes_s": round(s_n, 3), "certificate_s": round(s_c, 3), "visible": got[0]}
        res["layouts"][label] = lay
    return res


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    if len(sys.argv) > 2:
        print(json.dumps(main(n, Path(sys.argv[2])), indent=1))
    else:
        with tempfile.TemporaryDirectory() as d:
            print(json.dumps(main(n, Path(d)), indent=1))
