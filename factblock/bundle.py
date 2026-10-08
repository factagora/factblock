"""Load a bundle (SPEC 5.1): manifest plus node, edge, resolution tables as lists of dicts."""
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional, Union

INSTANT_KEYS = ("asserted_at", "valid_from", "valid_to", "known_at", "decided_at")


Instant = Union[str, date, datetime]   # '2024-05-01', '2024-05-01T12:00:00Z', a date, or a datetime (naive = UTC)


def parse_instant(v: Optional[Instant]) -> Optional[datetime]:
    """An aware datetime from an ISO 8601 string, a datetime or a date (midnight UTC). Naive means UTC. None stays None."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day, tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"not an instant: {v!r}. Use ISO 8601, e.g. '2024-05-01' (end of that day for as_of) or '2024-05-01T12:00:00Z'") from None
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
    """A FactBlock bundle read into memory: a folder with factblock.json plus nodes, edges and resolutions
    (JSONL or Parquet). Every read function takes a path or a Bundle; pass a Bundle to read the files once."""

    def __init__(self, path):
        self.path = Path(path)
        mpath = self.path / "factblock.json"
        if not mpath.exists():
            raise FileNotFoundError(f"no FactBlock bundle at {self.path}: factblock.json is missing. "
                                    f"Make one with `factblock sample {self.path}` or `factblock extract <text> --observed-at <date> -o {self.path}`")
        self.manifest = json.loads(mpath.read_text())
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


BundleLike = Union[str, "os.PathLike[str]", Bundle]   # a bundle folder path, or a Bundle already read


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
    # Rows first, manifest last and atomically (os.replace): a reader never sees a batch declared whose
    # rows are not there yet, and a crash mid-append leaves the old manifest in place.
    for name in ("nodes", "edges", "resolutions"):
        rows = result.get(name, [])
        if name in tables and (rows or (mode == "w" and name != "resolutions")):
            with (out / tables[name]).open(mode) as f:
                f.write("".join(json.dumps({k: v for k, v in r.items() if not k.startswith("_")}, default=lambda d: d.isoformat()) + "\n" for r in rows))
    tmp = mpath.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=1) + "\n")
    os.replace(tmp, mpath)
    return out
