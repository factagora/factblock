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
TARGETS = ("edge", "target_id", "path")   # the schema's payload oneOf: exactly one
assert len(measures) == 4
for n in measures:
    assert set(schema["required"]) <= n.keys() and n["kind"] == props["kind"]["const"] and n["fact_key"].startswith("measure.")
    assert set(props["fact_value"]["required"]) <= n["fact_value"].keys()
    assert sum(t in n["payload"] for t in TARGETS) == 1, n["id"]
    if "edge" in n["payload"]:   # the schema's if/then: an edge measurement also carries grade and horizon
        assert set(props["payload"]["properties"]["edge"]["required"]) <= n["payload"]["edge"].keys()
        assert set(schema["then"]["properties"]["fact_value"]["required"]) <= n["fact_value"].keys() and n["fact_value"]["grade"] in range(4)
nodes = {json.loads(l)["id"] for l in (SAMPLE / "nodes.jsonl").read_text().splitlines()}
node_measures = [n for n in measures if "target_id" in n["payload"]]
assert len(node_measures) == 2 and all(n["payload"]["target_id"] in nodes for n in node_measures)
assert [o["required"] for o in props["payload"]["oneOf"]] == [["edge"], ["target_id"]]

assert factblock.resolve(SAMPLE, KEY, "2026-09-15")["reason"] == "not_yet"
assert factblock.resolve(SAMPLE, KEY, "2026-10-10")["value"]["grade"] == 1
assert factblock.resolve(SAMPLE, KEY, "2026-10-21")["value"]["grade"] == 2   # latest_observed: re-measured
NODE_KEY = "measure.claim:frost-warning.independent_sources"   # a measurement whose target is a node reads the same way
assert factblock.resolve(SAMPLE, NODE_KEY, "2026-09-10")["reason"] == "not_yet"
assert factblock.resolve(SAMPLE, NODE_KEY, "2026-09-20")["value"]["independent_sources"] == 1
assert factblock.resolve(SAMPLE, NODE_KEY, "2026-09-26")["value"]["independent_sources"] == 2
print("PASS measurement: sample validates, 2 edge and 2 node vintages match the schema's required fields, resolve takes the later one")
