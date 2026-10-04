"""The one check that fails if the reader or validator breaks: the sample bundle validates,
and the same query answers differently at three instants (SPEC 2, 4). Run: uv run python tests/test_rates.py"""
import copy
import json
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
assert ids(may) == ["c1", "c2"] and may.certificate["masked"] == {"node": 2, "edge": 2}, may.certificate
aug = factblock.scan(RATES, "2024-08-01")
assert ids(aug) == ["c1", "c2", "c3"] and aug.certificate["masked"] == {"node": 1, "edge": 1}
octo = factblock.scan(RATES, "2024-10-01")
assert ids(octo) == ["c1", "c2", "c3", "c4"] and "masked" not in octo.certificate
sup = dict(zip(octo.nodes.column("id").to_pylist(), octo.nodes.column("superseded_by").to_pylist()))
assert sup == {"c1": "c4", "c2": None, "c3": None, "c4": None}, sup
assert octo.certificate["backfill"] == {"batches": 3, "rows": 7}
assert may.certificate["backfill"] == {"batches": 1, "rows": 3}

# valid_at selects content: as known in October, what held in June is c1 and c2 only (c3 asserted June 20 holds)
june = factblock.scan(RATES, "2024-10-01", valid_at="2024-06-01")
assert ids(june) == ["c1", "c2"], ids(june)

# the validator must catch a broken invariant: a block whose batch does not exist
b = factblock.Bundle(RATES)
bad = copy.deepcopy(b)
bad.nodes[0]["attestation"] = {"ledger": "tckg/0.2.0", "batch": "nope"}
failed = {c.check_id for c in factblock.validate(bad) if not c.ok}
assert failed == {"I2.batch_exists"}, failed

try:
    factblock.scan(RATES, None)
    raise AssertionError("as_of default must not exist")
except ValueError:
    pass
print("PASS factblock: validate 11/11, scan at three instants, supersession, certificate, valid_at")
