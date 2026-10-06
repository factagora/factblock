"""SPEC section 4: as-of read with certificate and superseded_by. Arrow tables out."""
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import pyarrow as pa

from .bundle import Bundle, parse_instant

JSON_COLS = ("payload", "properties", "fact_value", "attestation", "value", "evidence")   # free-form or mixed-type: out as JSON strings


def _as_of(v):
    """A date means the end of that day in UTC (SPEC 4.1)."""
    if isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return parse_instant(v + "T23:59:59.999999+00:00")
    return parse_instant(v)


def _visible(r, as_of, valid_at):
    if r["known_at"] > as_of:
        return False
    if "asserted_at" not in r:          # resolutions have no validity interval
        return True
    to = r.get("valid_to")
    return r["asserted_at"] <= valid_at and r["valid_from"] <= valid_at and (to is None or valid_at < to)


def _table(rows):
    """pyarrow infers poorly on free-form dicts, so JSON columns go out as strings."""
    rows = [{**{k: v for k, v in r.items() if not k.startswith("_")}, **{k: json.dumps(r[k]) for k in JSON_COLS if k in r and r[k] is not None}} for r in rows]
    return pa.Table.from_pylist(rows)


@dataclass
class Scan:
    nodes: pa.Table
    edges: pa.Table
    resolutions: pa.Table
    certificate: dict


def visible(bundle, as_of, valid_at=None):
    """The rows an as-of read shows, as plain dicts, plus the certificate: what scan() does before it
    builds Arrow tables. recall() and the projections use this; scan() wraps it."""
    if as_of is None:
        raise ValueError("as_of has no default: every read says which instant it asks about (SPEC 4.1)")
    b = bundle if isinstance(bundle, Bundle) else Bundle(bundle)
    t = _as_of(as_of)
    v = parse_instant(valid_at) if valid_at else t   # SPEC 4.1: valid_at defaults to as_of
    nodes = [r for r in b.nodes if _visible(r, t, v)]
    edges = [r for r in b.edges if _visible(r, t, v)]
    res = [r for r in b.resolutions if _visible(r, t, v)]

    superseded = {e["target_id"]: e["source_id"] for e in edges if e["edge_type"] == "SUPERSEDES"}
    nodes = [{**r, "superseded_by": superseded.get(r["id"])} for r in nodes]

    # SPEC 4.2: masked = learned after as_of (hindsight blocked); not_in_force = known by then but not in force at valid_at
    masked, not_in_force = {}, {}
    for k, every, shown in (("node", b.nodes, nodes), ("edge", b.edges, edges), ("resolution", b.resolutions, res)):
        later = sum(1 for r in every if r["known_at"] > t)
        if later:
            masked[k] = later
        if len(every) - len(shown) - later:
            not_in_force[k] = len(every) - len(shown) - later
    batches = {r["attestation"]["batch"] for r in nodes + edges + res if r.get("attestation", {}).get("batch")}
    rows = sum(1 for r in nodes + edges + res if r.get("attestation", {}).get("batch"))
    cert = {"as_of": t.isoformat(), "read_at": datetime.now(timezone.utc).isoformat()}
    cert["valid_at"] = v.isoformat()
    if masked:
        cert["masked"] = masked
    if not_in_force:
        cert["not_in_force"] = not_in_force
    if batches:
        cert["backfill"] = {"batches": len(batches), "rows": rows}
    return nodes, edges, res, cert


def scan(bundle, as_of, valid_at=None) -> Scan:
    nodes, edges, res, cert = visible(bundle, as_of, valid_at)
    return Scan(_table(nodes), _table(edges), _table(res), cert)
