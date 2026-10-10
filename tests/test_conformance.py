"""The Python reader and the DuckDB macros give the answers in conformance/cases.jsonl: which blocks are visible
as of each instant, what replaced each one, and the latest verdict on each. A reader in another language passes
when it gives the same. Run: uv run python tests/test_conformance.py"""
import json
import pathlib
import sys
import tempfile

import duckdb

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import factblock  # noqa: E402

cases = [json.loads(l) for l in (ROOT / "conformance" / "cases.jsonl").read_text().splitlines() if l.strip()]
con = duckdb.connect()
con.execute((ROOT / "duckdb" / "factblock.sql").read_text())
parquet = {}
with tempfile.TemporaryDirectory() as tmp:
    for c in cases:
        bundle, why = ROOT / c["bundle"], f'{c["bundle"]} as of {c["as_of"]}: {c["why"]}'
        s = factblock.scan(bundle, c["as_of"], c["valid_at"])
        assert sorted([r["id"], r["superseded_by"]] for r in s.to_dicts("nodes")) == c["nodes"], ("python", why)
        latest = {}
        for v in sorted(s.to_dicts("resolutions"), key=lambda v: (v["decided_at"], v["known_at"])):
            latest[v["target_id"]] = v["outcome"]
        assert latest == c["verdicts"], ("python verdicts", why, latest)

        pq = parquet.get(c["bundle"]) or str(factblock.write_parquet(bundle, pathlib.Path(tmp) / str(len(parquet))))
        parquet[c["bundle"]] = pq
        at = "factblock_day(CAST(? AS DATE))"
        if c["valid_at"]:
            rows = con.execute(f"SELECT id, superseded_by FROM factblock_nodes(?, {at}, valid_at := CAST(? AS TIMESTAMPTZ))", [pq, c["as_of"], c["valid_at"]]).fetchall()
        else:
            rows = con.execute(f"SELECT id, superseded_by FROM factblock_nodes(?, {at})", [pq, c["as_of"]]).fetchall()
        assert sorted([i, s_] for i, s_ in rows) == c["nodes"], ("duckdb", why, sorted(rows))
        if (pathlib.Path(pq) / "resolutions.parquet").exists():
            got = dict(con.execute(f"SELECT target_id, outcome FROM factblock_verdicts(?, {at})", [pq, c["as_of"]]).fetchall())
        else:
            got = {}
        assert got == c["verdicts"], ("duckdb verdicts", why, got)
print(f"PASS conformance: python and duckdb agree with {len(cases)} cases (replacement announced before it takes effect, learned late, replaced twice, verdicts)")
