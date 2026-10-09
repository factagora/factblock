"""Load a bundle (SPEC 5.1): manifest plus node, edge, resolution tables as lists of dicts."""
import copy
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
        manifest = json.loads(mpath.read_text())
        tables = manifest.get("tables", {})
        self._load(manifest, *(_read_table(self.path / tables.get(t, f"{t}.jsonl")) for t in ("nodes", "edges", "resolutions")))

    def _load(self, manifest, nodes, edges, resolutions):
        self.manifest, self.nodes, self.edges, self.resolutions = manifest, nodes, edges, resolutions
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


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _label(name, r):
    return r.get("id") or (f"resolution of {r.get('target_id')}" if name == "resolutions" else f"{r.get('source_id')}->{r.get('target_id')}")


IDENTITY = {"nodes": lambda r: r["id"],
            "edges": lambda r: (r["source_id"], r["target_id"], r["edge_type"], parse_instant(r["asserted_at"])),
            "resolutions": lambda r: (r["target_id"], parse_instant(r["decided_at"]))}


def _content(r):
    """What a row says, without when it was learned or who attests it."""
    return {k: parse_instant(v) if k in INSTANT_KEYS else v for k, v in r.items() if k not in ("known_at", "attestation") and v is not None}


def write_bundle(result: dict, out, append: bool = False, *, declared_by: str = "process:factblock-write") -> Path:
    """Put {"manifest"?, "nodes", "edges", "resolutions"?} on disk as a JSONL bundle. With append=True and a bundle
    already at `out`, rows are added and the manifest's declarations are merged, so a folder grows
    one batch at a time and stays valid.

    Rows may carry instants as strings, dates or datetimes. A node or edge without `valid_from` gets its
    `asserted_at`. A row without `attestation` goes under a backfill batch declared at its `known_at`
    (SPEC 6: the writer declares when it learned the row, it never claims to be a ledger); a row without
    `known_at` is an error. With append=True a row the folder already has (same identity, SPEC 6.1) is skipped,
    so re-running an import adds nothing; the same identity with different content is an error, because blocks
    are never edited. append=False replaces the folder's tables. The whole bundle is validated before anything
    is written: a failing check raises ValueError and leaves the folder as it was. `result` is not modified.
    Returns the folder path."""
    from .validate import validate   # validate imports this module
    out = Path(out)
    mpath = out / "factblock.json"
    old = Bundle(out) if append and mpath.exists() else None
    now = datetime.now(timezone.utc)
    manifest = copy.deepcopy(result.get("manifest") or {})
    manifest.setdefault("factblock_version", "1.0-draft.1"); manifest.setdefault("namespace", "local")
    decl = manifest.setdefault("declarations", {})
    for key in ("facts", "backfills", "edge_types"):
        decl.setdefault(key, [])
    decl.setdefault("embedding", None)
    declared = {b["batch"] for b in decl["backfills"]} | set(old.backfills if old else ())

    # SPEC 6.1 identity: writing a row the folder already has is a no-op, so re-running an import is safe
    have = {n: {IDENTITY[n](x): x for x in getattr(old, n)} for n in IDENTITY} if old else {n: {} for n in IDENTITY}
    rows, skipped = {}, {}
    for name in ("nodes", "edges", "resolutions"):
        rows[name] = []
        for r in result.get(name) or []:
            r = {k: v for k, v in r.items() if not k.startswith("_")}
            for k in INSTANT_KEYS:
                if r.get(k) is not None:
                    r[k] = _iso(parse_instant(r[k]))
            if name != "resolutions":
                r.setdefault("valid_from", r.get("asserted_at")); r.setdefault("valid_to", None)
            prev = have[name].get(IDENTITY[name](r))
            if prev is not None:
                if _content(prev) != _content(r):
                    raise ValueError(f"not written to {out}: {name} row {_label(name, r)} is already in the bundle with different content. "
                                     f"Blocks are never edited: write the change as a new block with its own id and replaces/SUPERSEDES")
                skipped[name] = skipped.get(name, 0) + 1
                continue
            if not r.get("attestation"):
                if not r.get("known_at"):
                    raise ValueError(f"{name} row {_label(name, r)} has no known_at: set it to when you learned the row "
                                     f"(the day it reached you), or to its asserted_at for material from the past")
                batch = f"known-{parse_instant(r['known_at']).strftime('%Y%m%dT%H%M%SZ')}"
                r["attestation"] = {"batch": batch}
                if batch not in declared:
                    declared.add(batch)
                    decl["backfills"].append({"batch": batch, "declared_known_at": r["known_at"], "reason": "known_at given by the writer",
                                              "declared_by": declared_by, "captured_at": _iso(now)})
            rows[name].append(r)

    if old:
        merged = copy.deepcopy(old.manifest)
        for key in ("facts", "backfills", "edge_types"):
            have = {json.dumps(x, sort_keys=True, default=_iso) for x in merged["declarations"].get(key, [])}
            merged["declarations"][key] = merged["declarations"].get(key, []) + [x for x in decl[key] if json.dumps(x, sort_keys=True, default=_iso) not in have]
        merged["exported_as_of"] = manifest.get("exported_as_of", merged.get("exported_as_of"))
        manifest = json.loads(json.dumps(merged, default=_iso))
    tables = manifest.setdefault("tables", {})
    tables.setdefault("nodes", "nodes.jsonl"); tables.setdefault("edges", "edges.jsonl")
    if rows["resolutions"]:
        tables.setdefault("resolutions", "resolutions.jsonl")

    # check the bundle as it will be on disk, before touching the disk
    probe = Bundle.__new__(Bundle); probe.path = out
    parsed = {n: [{k: parse_instant(v) if k in INSTANT_KEYS else v for k, v in r.items()} for r in rows[n]] for n in rows}
    probe._load(json.loads(json.dumps(manifest)), *((getattr(old, n) if old else []) + parsed[n] for n in ("nodes", "edges", "resolutions")))
    failed = [c for c in validate(probe) if not c.ok]
    if failed:
        raise ValueError(f"not written to {out}, the bundle would be invalid: " + "; ".join(f"{c.check_id}: {c.detail}" for c in failed))

    # Rows first, manifest last and atomically (os.replace): a reader never sees a batch declared whose
    # rows are not there yet, and a crash mid-append leaves the old manifest in place.
    out.mkdir(parents=True, exist_ok=True)
    mode = "a" if old else "w"
    for name in ("nodes", "edges", "resolutions"):
        if name in tables and (rows[name] or (mode == "w" and name != "resolutions")):
            with (out / tables[name]).open(mode) as f:
                f.write("".join(json.dumps(r, default=_iso) + "\n" for r in rows[name]))
    tmp = mpath.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=1) + "\n")
    os.replace(tmp, mpath)
    return out
