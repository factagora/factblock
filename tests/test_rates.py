"""The one check that fails if the reader, validator, or resolver breaks: the sample bundle validates,
the same query answers differently at three instants, and resolve follows the declared policy
(SPEC 2, 4). Run: uv run python tests/test_rates.py"""
import copy
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import factblock  # noqa: E402

RATES = pathlib.Path(__file__).resolve().parents[1] / "samples" / "rates"

checks = factblock.validate(RATES)
assert all(c.ok for c in checks), [c for c in checks if not c.ok]
assert len(checks) == 11

ids = lambda s: sorted(s.nodes.column("id").to_pylist())  # noqa: E731
may = factblock.scan(RATES, "2024-05-01")
assert ids(may) == ["c1", "c2"] and may.certificate["masked"] == {"node": 4, "edge": 2, "resolution": 3}, may.certificate
aug = factblock.scan(RATES, "2024-08-01")
assert ids(aug) == ["c1", "c2", "c3"] and aug.certificate["masked"] == {"node": 3, "edge": 1, "resolution": 2}
octo = factblock.scan(RATES, "2024-10-01")
assert ids(octo) == ["c1", "c2", "c3", "c4", "t1", "t2"] and octo.certificate["masked"] == {"resolution": 1}   # the December re-resolution of c1
sup = dict(zip(octo.nodes.column("id").to_pylist(), octo.nodes.column("superseded_by").to_pylist()))
assert sup["c1"] == "c4" and all(v is None for k, v in sup.items() if k != "c1"), sup
assert octo.certificate["backfill"] == {"batches": 3, "rows": 9}
assert may.certificate["backfill"] == {"batches": 1, "rows": 3}

# valid_at selects content: as known in October, what held in June is c1 and c2 only
june = factblock.scan(RATES, "2024-10-01", valid_at="2024-06-01")
assert ids(june) == ["c1", "c2"], ids(june)

# resolve follows the declared policy and says which kind of nothing it is
r = lambda k, t, **kw: factblock.resolve(RATES, k, t, **kw)  # noqa: E731
assert (r("belief:fed:direction", "2024-05-01")["value"]) == {"direction": "up"}
assert (r("belief:fed:direction", "2024-10-01")["value"]) == {"direction": "down"}       # latest_valid
assert (r("belief:fed:direction", "2024-10-01", valid_at="2024-06-01")["value"]) == {"direction": "up"}
assert r("belief:fed:direction", "2024-02-01")["reason"] == "undeclared_fact"               # declared 2024-03-01
assert r("belief:fed:direction", "2024-02-01", rules_as_of="2024-10-01")["reason"] == "not_yet"   # rule applies, nothing known yet
assert r("nobody:declared:this", "2024-10-01")["reason"] == "undeclared_fact"
assert r("belief:nvda:direction", "2024-10-01")["reason"] == "no_data"
assert r("belief:tsla:direction", "2024-05-01")["reason"] == "not_yet"
c = r("belief:tsla:direction", "2024-10-01")
assert c["status"] == "no_answer" and c["reason"] == "unresolved_conflict" and len(c["candidates"]) == 2, c
assert r("belief:fed:direction", "2024-10-01")["certificate"]["backfill"] == {"batches": 2, "rows": 2}

# the validator must catch a broken invariant: a block whose batch does not exist
bad = copy.deepcopy(factblock.Bundle(RATES))
bad.nodes[0]["attestation"] = {"ledger": "tckg/0.2.0", "batch": "nope"}
failed = {c.check_id for c in factblock.validate(bad) if not c.ok}
assert failed == {"I2.batch_exists"}, failed
# SPEC 6: a writer that is not a ledger attests with a declared batch alone; no attestation at all fails
ok = copy.deepcopy(factblock.Bundle(RATES))
ok.nodes[0]["attestation"] = {"batch": ok.nodes[0]["attestation"]["batch"]}
assert all(c.ok for c in factblock.validate(ok)), [c for c in factblock.validate(ok) if not c.ok]
ok.nodes[0]["attestation"] = {}
assert {c.check_id for c in factblock.validate(ok) if not c.ok} == {"I2.attested"}

for f in (lambda: factblock.scan(RATES, None), lambda: factblock.resolve(RATES, "x", None)):
    try:
        f()
        raise AssertionError("as_of default must not exist")
    except ValueError:
        pass
assert factblock.scan(RATES, "2024-10-01").resolutions.num_rows == 2 and factblock.scan(RATES, "2025-01-01").resolutions.num_rows == 3
print("PASS factblock: validate 11/11, scan at three instants, supersession, certificate, valid_at, resolve 10 cases, verdict rows masked by known_at")

# Parquet profile: the same bundle written as Parquet validates and answers identically (SPEC 5.3)
import tempfile  # noqa: E402
with tempfile.TemporaryDirectory() as d:
    pq_dir = factblock.write_parquet(RATES, d)
    assert sorted(x.name for x in pq_dir.iterdir()) == ["edges.parquet", "factblock.json", "nodes.parquet", "resolutions.parquet"]
    assert all(c.ok for c in factblock.validate(pq_dir)), [c for c in factblock.validate(pq_dir) if not c.ok]
    for t in ("2024-05-01", "2024-08-01", "2024-10-01"):
        a, b = factblock.scan(RATES, t), factblock.scan(pq_dir, t)
        assert ids(a) == ids(b) and a.certificate.get("masked") == b.certificate.get("masked"), t
        assert a.certificate.get("backfill") == b.certificate.get("backfill")
    ra, rb = factblock.resolve(RATES, "belief:fed:direction", "2024-10-01"), factblock.resolve(pq_dir, "belief:fed:direction", "2024-10-01")
    assert ra["value"] == rb["value"] and ra["policy"] == rb["policy"]
    # payload and the free-form fields survive the JSON-string column
    c1 = next(n for n in factblock.Bundle(pq_dir).nodes if n["id"] == "c1")
    assert c1["payload"] == {"about": {"start": "2024-03"}} and c1["fact_value"] == {"direction": "up"} and c1["author"] == "human:analyst-1", c1
    # an engine reads the file directly: rows sorted by known_at, so an as-of read is a prefix
    import pyarrow.parquet as pq
    t = pq.read_table(pq_dir / "nodes.parquet")
    ks = t.column("known_at").to_pylist()
    assert ks == sorted(ks) and str(t.schema.field("known_at").type) == "timestamp[us, tz=UTC]"
print("PASS factblock parquet: write, validate, scan x3, resolve, round-trip fields, sorted by known_at")

# the real sample: one public figure's two years of statements, links and settled calls, read at three instants
CRAMER = pathlib.Path(__file__).resolve().parents[1] / "samples" / "cramer"
assert all(c.ok for c in factblock.validate(CRAMER)), [c for c in factblock.validate(CRAMER) if not c.ok]
early = factblock.scan(CRAMER, "2024-10-01")
assert early.nodes.num_rows == 58 and early.certificate["masked"]["node"] == 2033 and early.resolutions.num_rows == 0, early.certificate
assert factblock.scan(CRAMER, "2025-06-01").resolutions.num_rows == 197
chain = factblock.why(CRAMER, "1b77a1a885470207", "2026-09-10")["chain"]
assert len(chain) == 5 and {r["role"] for r in chain} == {"subject", "effect"}, chain
assert factblock.why(CRAMER, "1b77a1a885470207", "2025-01-01")["reason"] == "not_yet"
assert factblock.recall(CRAMER, "Nvidia data center", "2025-01-01")["matched"] == 21
assert len(factblock.to_claimreview(CRAMER, "2025-06-01")["@graph"]) == 197
print("PASS samples/cramer: validate, 58 blocks known by 2024-10, 197 verdicts by 2025-06, a five-block chain, recall, ClaimReview")
