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
        # every case checks superseded_for; a case without the field expects none (SPEC 4.3)
        got = {r["id"]: [x["by"] for x in r["superseded_for"]] for r in s.to_dicts("nodes") if r.get("superseded_for")}
        assert got == c.get("superseded_for", {}), ("python superseded_for", why, got)
        if "namespaces" in c:
            got = {r["id"]: r["namespace"] for r in s.to_dicts("nodes") if r.get("namespace") is not None}
            assert got == c["namespaces"], ("python namespaces", why, got)

        pq = parquet.get(c["bundle"]) or str(factblock.write_parquet(bundle, pathlib.Path(tmp) / str(len(parquet))))
        parquet[c["bundle"]] = pq
        at = "factblock_day(CAST(? AS DATE))"
        if c["valid_at"]:
            rows = con.execute(f"SELECT id, superseded_by FROM factblock_nodes(?, {at}, valid_at := CAST(? AS TIMESTAMPTZ))", [pq, c["as_of"], c["valid_at"]]).fetchall()
        else:
            rows = con.execute(f"SELECT id, superseded_by FROM factblock_nodes(?, {at})", [pq, c["as_of"]]).fetchall()
        assert sorted([i, s_] for i, s_ in rows) == c["nodes"], ("duckdb", why, sorted(rows))
        got = {i: [x["by"] for x in f] for i, f in con.execute(f"SELECT id, superseded_for FROM factblock_nodes(?, {at}{', valid_at := CAST(? AS TIMESTAMPTZ)' if c['valid_at'] else ''}) WHERE superseded_for IS NOT NULL",
                                                                [pq, c["as_of"]] + ([c["valid_at"]] if c["valid_at"] else [])).fetchall()}
        assert got == c.get("superseded_for", {}), ("duckdb superseded_for", why, got)
        if "namespaces" in c:
            got = dict(con.execute(f"SELECT id, namespace FROM factblock_nodes(?, {at}) WHERE namespace IS NOT NULL", [pq, c["as_of"]]).fetchall())
            assert got == c["namespaces"], ("duckdb namespaces", why, got)
        if (pathlib.Path(pq) / "resolutions.parquet").exists():
            got = dict(con.execute(f"SELECT target_id, outcome FROM factblock_verdicts(?, {at})", [pq, c["as_of"]]).fetchall())
        else:
            got = {}
        assert got == c["verdicts"], ("duckdb verdicts", why, got)
print(f"PASS conformance: python and duckdb agree with {len(cases)} cases (replacement announced before it takes effect, learned late, replaced twice, verdicts, namespace set and absent, replaced for some cases only)")
