"""Load a bundle (SPEC 5.1): manifest plus node, edge, resolution tables as lists of dicts."""
import json
from datetime import datetime, timezone
from pathlib import Path

INSTANT_KEYS = ("asserted_at", "valid_from", "valid_to", "known_at", "decided_at")


def parse_instant(v):
    """RFC 3339 string -> aware datetime. None stays None."""
    if v is None or isinstance(v, datetime):
        return v
    d = datetime.fromisoformat(v.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _read_table(path: Path) -> list[dict]:
    if not path.exists():
        return []
    if path.suffix == ".parquet":
        import pyarrow.parquet as pq
        from .parquet import decode_parquet_row
        rows = [decode_parquet_row(r) for r in pq.read_table(path).to_pylist()]
    else:
        with path.open() as f:
            rows = [json.loads(line) for line in f if line.strip()]
    for r in rows:
        for k in INSTANT_KEYS:
            if k in r:
                r[k] = parse_instant(r[k])
    return rows


class Bundle:
    def __init__(self, path):
        self.path = Path(path)
        self.manifest = json.loads((self.path / "factblock.json").read_text())
        tables = self.manifest.get("tables", {})
        self.nodes = _read_table(self.path / tables.get("nodes", "nodes.jsonl"))
        self.edges = _read_table(self.path / tables.get("edges", "edges.jsonl"))
        self.resolutions = _read_table(self.path / tables.get("resolutions", "resolutions.jsonl"))
        d = self.manifest.get("declarations", {})
        self.facts = {}
        for f in d.get("facts", []):
            f["declared_at"] = parse_instant(f.get("declared_at"))
            self.facts.setdefault(f["fact_key"], []).append(f)
        self.backfills = {b["batch"]: b for b in d.get("backfills", [])}
        for b in self.backfills.values():
            b["declared_known_at"] = parse_instant(b["declared_known_at"])
        self.edge_types = {e["edge_type"]: e["family"] for e in d.get("edge_types", [])}

    def blocks(self):
        """Every block with a table label: nodes, edges, resolutions."""
        for r in self.nodes:
            yield "node", r
        for r in self.edges:
            yield "edge", r
        for r in self.resolutions:
            yield "resolution", r


def write_bundle(result: dict, out, append: bool = False) -> Path:
    """Put {"manifest", "nodes", "edges", "resolutions"?} on disk as a JSONL bundle. With append=True and a bundle
    already at `out`, rows are added and the manifest's declarations are merged, so a folder grows
    one batch at a time and stays valid."""
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    mpath = out / "factblock.json"
    manifest = result["manifest"]
    if append and mpath.exists():
        old = json.loads(mpath.read_text())
        for key in ("facts", "backfills", "edge_types"):
            have = {json.dumps(x, sort_keys=True) for x in old["declarations"].get(key, [])}
            old["declarations"][key] = old["declarations"].get(key, []) + [x for x in manifest["declarations"].get(key, []) if json.dumps(x, sort_keys=True) not in have]
        old["exported_as_of"] = manifest.get("exported_as_of", old.get("exported_as_of"))
        manifest = old
        mode = "a"
    else:
        mode = "w"
    tables = manifest.setdefault("tables", {})
    tables.setdefault("nodes", "nodes.jsonl"); tables.setdefault("edges", "edges.jsonl")
    if result.get("resolutions"):
        tables.setdefault("resolutions", "resolutions.jsonl")
    mpath.write_text(json.dumps(manifest, indent=1) + "\n")
    for name in ("nodes", "edges", "resolutions"):
        rows = result.get(name, [])
        if name in tables and (rows or (mode == "w" and name != "resolutions")):
            with (out / tables[name]).open(mode) as f:
                f.write("".join(json.dumps(r, default=lambda d: d.isoformat()) + "\n" for r in rows))
    return out
