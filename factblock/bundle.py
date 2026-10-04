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
        rows = pq.read_table(path).to_pylist()
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
