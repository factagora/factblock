"""The measurement sample (SPEC 3.8, informative) stays a plain bundle: it validates, its measurement nodes
carry what schemas/measurement.v1.schema.json requires, and resolve picks the vintage learned last.
Run: uv run python tests/test_measurement.py"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import factblock  # noqa: E402

SAMPLE = ROOT / "samples" / "measurement"
KEY = "measure.factor:rain.causes.entity:harvest.30d"

assert all(c.ok for c in factblock.validate(SAMPLE)), [c for c in factblock.validate(SAMPLE) if not c.ok]

# shortcut: checks the schema's required keys only, no jsonschema dependency; upgrade if the schema grows rules
schema = json.loads((ROOT / "schemas" / "measurement.v1.schema.json").read_text())
props = schema["properties"]
measures = [json.loads(l) for l in (SAMPLE / "nodes.jsonl").read_text().splitlines() if '"measure.' in l and '"kind": "claim"' in l]
assert len(measures) == 2
for n in measures:
    assert set(schema["required"]) <= n.keys() and n["kind"] == props["kind"]["const"] and n["fact_key"].startswith("measure.")
    assert set(props["payload"]["properties"]["edge"]["required"]) <= n["payload"]["edge"].keys()
    assert set(props["fact_value"]["required"]) <= n["fact_value"].keys() and n["fact_value"]["grade"] in range(4)

assert factblock.resolve(SAMPLE, KEY, "2026-09-15")["reason"] == "not_yet"
assert factblock.resolve(SAMPLE, KEY, "2026-10-10")["value"]["grade"] == 1
assert factblock.resolve(SAMPLE, KEY, "2026-10-21")["value"]["grade"] == 2   # latest_observed: re-measured
print("PASS measurement: sample validates, 2 vintages match the schema's required fields, resolve takes the later one")
