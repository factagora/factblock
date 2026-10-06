"""SPEC 5.3: the Parquet profile. One file per table, one explicit Arrow schema per
table, rows sorted by known_at so an as-of read is a prefix scan. Free-form
columns (payload, properties, fact_value, evidence) are JSON strings; fields the
schema does not know go to `extra` as JSON, so nothing is dropped (SPEC 7)."""
import json
import shutil
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from .bundle import Bundle

TS = pa.timestamp("us", tz="UTC")
ATTESTATION = pa.struct([("ledger", pa.string()), ("batch", pa.string())])
JSON_COLS = {"payload", "properties", "fact_value", "evidence", "value", "extra"}   # stored as JSON strings

SCHEMAS = {
    "nodes": pa.schema([
        ("id", pa.string()), ("kind", pa.string()), ("space", pa.string()), ("statement", pa.string()),
        ("category", pa.string()), ("payload", pa.string()),
        ("asserted_at", TS), ("valid_from", TS), ("valid_to", TS), ("known_at", TS),
        ("attestation", ATTESTATION), ("fact_key", pa.string()), ("fact_value", pa.string()),
        ("embedding", pa.list_(pa.float32())), ("author", pa.string()), ("extra", pa.string()),
    ]),
    "edges": pa.schema([
        ("source_id", pa.string()), ("target_id", pa.string()), ("edge_type", pa.string()),
        ("confidence", pa.float64()), ("lag", pa.string()), ("mechanism", pa.string()), ("properties", pa.string()),
        ("asserted_at", TS), ("valid_from", TS), ("valid_to", TS), ("known_at", TS),
        ("attestation", ATTESTATION), ("author", pa.string()), ("extra", pa.string()),
    ]),
    "resolutions": pa.schema([
        ("target_id", pa.string()), ("value", pa.string()), ("decided_at", TS), ("known_at", TS),
        ("attestation", ATTESTATION), ("resolver", pa.string()), ("method", pa.string()),
        ("criteria", pa.string()), ("outcome", pa.string()), ("evidence", pa.string()), ("extra", pa.string()),
    ]),
}
SORT = {"nodes": ("known_at", "id"), "edges": ("known_at", "source_id", "target_id", "edge_type"), "resolutions": ("known_at", "target_id")}


def _row(r: dict, schema: pa.Schema) -> dict:
    known = set(schema.names) - {"extra"}
    out = {k: r.get(k) for k in known}
    for k in JSON_COLS & known:
        if out.get(k) is not None:
            out[k] = json.dumps(out[k])
    extra = {k: v for k, v in r.items() if k not in known}
    out["extra"] = json.dumps(extra, default=str) if extra else None
    return out


def to_table(rows: list[dict], name: str) -> pa.Table:
    # SPEC 5.3: by UTC instant, ties by the table's identity columns. Arrow compares timestamps as UTC
    # int64; sorting the Python values as strings put "+09:00" rows out of instant order.
    t = pa.Table.from_pylist([_row(r, SCHEMAS[name]) for r in rows], schema=SCHEMAS[name])
    return t.sort_by([(k, "ascending") for k in SORT[name]])


def write_parquet(bundle, out) -> Path:
    """A JSONL (or Parquet) bundle to a Parquet bundle in `out`. Manifest copied, tables renamed."""
    b = bundle if isinstance(bundle, Bundle) else Bundle(bundle)
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    manifest = dict(b.manifest); manifest["tables"] = {}
    for name, rows in (("nodes", b.nodes), ("edges", b.edges), ("resolutions", b.resolutions)):
        if not rows and name == "resolutions":
            continue
        pq.write_table(to_table(rows, name), out / f"{name}.parquet", compression="zstd")
        manifest["tables"][name] = f"{name}.parquet"
    (out / "factblock.json").write_text(json.dumps(manifest, indent=1, default=str) + "\n")
    return out


def decode_parquet_row(r: dict) -> dict:
    """Undo _row: JSON strings back to values, extra merged back, absent fields dropped."""
    extra = r.pop("extra", None)
    out = {}
    for k, v in r.items():
        if v is None:
            continue
        if k in JSON_COLS:
            v = json.loads(v)
        out[k] = v
    if extra:
        out.update(json.loads(extra))
    return out
