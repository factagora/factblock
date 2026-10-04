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
assert ids(may) == ["c1", "c2"] and may.certificate["masked"] == {"node": 4, "edge": 2}, may.certificate
aug = factblock.scan(RATES, "2024-08-01")
assert ids(aug) == ["c1", "c2", "c3"] and aug.certificate["masked"] == {"node": 3, "edge": 1}
octo = factblock.scan(RATES, "2024-10-01")
assert ids(octo) == ["c1", "c2", "c3", "c4", "t1", "t2"] and "masked" not in octo.certificate
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

for f in (lambda: factblock.scan(RATES, None), lambda: factblock.resolve(RATES, "x", None)):
    try:
        f()
        raise AssertionError("as_of default must not exist")
    except ValueError:
        pass
print("PASS factblock: validate 11/11, scan at three instants, supersession, certificate, valid_at, resolve 10 cases")
