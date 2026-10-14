"""SPEC section 4: as-of read with certificate, superseded_by and superseded_for. Arrow tables out."""
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone

import pyarrow as pa

from .bundle import Bundle, BundleLike, Instant, parse_instant

JSON_COLS = ("payload", "properties", "fact_value", "attestation", "value", "evidence", "applies_if", "superseded_for")   # free-form or mixed-type: out as JSON strings


def _as_of(v):
    """A date means the end of that day in UTC (SPEC 4.1), as a string or a date object."""
    if isinstance(v, date) and not isinstance(v, datetime):
        v = v.isoformat()
    if isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return parse_instant(v + "T23:59:59.999999+00:00")
    return parse_instant(v)


def _comparable(c):
    """One condition has the SPEC 3.1 shape: key, op, and a string value (or, for eq, a non-empty list of strings)."""
    v = c.get("value") if isinstance(c, dict) else None
    return (isinstance(c, dict) and isinstance(c.get("key"), str) and c["key"] != "" and c.get("op") in ("eq", "after", "before")
            and (isinstance(v, str) or c["op"] == "eq" and isinstance(v, list) and v != [] and all(isinstance(x, str) for x in v)))


def conditions(r):
    """A row's applies_if as comparable conditions (SPEC 3.1, 4.3): (key, op, values), an eq list as a set. Absent
    or null is none; a malformed applies_if is None, not comparable, so no replacement into or from it is total."""
    a = r.get("applies_if")
    if a is None:
        return set()
    if not isinstance(a, list) or not all(map(_comparable, a)):
        return None
    return {(c["key"], c["op"], tuple(sorted(set(c["value"]))) if isinstance(c["value"], list) else (c["value"],)) for c in a}


def _visible(r, as_of, valid_at):
    if r["known_at"] > as_of:
        return False
    if "asserted_at" not in r:          # resolutions have no validity interval
        return True
    to = r.get("valid_to")
    return r["valid_from"] <= valid_at and (to is None or valid_at < to)   # SPEC 4.1: asserted_at does not cap validity (retroactive rules)


def _table(rows):
    """pyarrow infers poorly on free-form dicts, so JSON columns go out as strings."""
    rows = [{**{k: v for k, v in r.items() if not k.startswith("_")}, **{k: json.dumps(r[k]) for k in JSON_COLS if k in r and r[k] is not None}} for r in rows]
    cols = list(dict.fromkeys(k for r in rows for k in r))   # from_pylist takes its columns from the first row only
    return pa.Table.from_pylist([{k: r.get(k) for k in cols} for r in rows])


@dataclass
class Scan:
    nodes: pa.Table
    edges: pa.Table
    resolutions: pa.Table
    certificate: dict

    def to_dicts(self, table: str = "nodes") -> list[dict]:
        """Use when you want rows, not Arrow: one table as dicts, with the JSON columns (payload, value, ...) parsed back."""
        return [{k: json.loads(v) if k in JSON_COLS and isinstance(v, str) else v for k, v in r.items()}
                for r in getattr(self, table).to_pylist()]


def visible(bundle: BundleLike, as_of: Instant, valid_at: Instant | None = None) -> tuple[list[dict], list[dict], list[dict], dict]:
    """The rows an as-of read shows, as plain dicts, plus the certificate: what scan() does before it
    builds Arrow tables. recall() and the projections use this; scan() wraps it."""
    if as_of is None:
        raise ValueError("as_of has no default: every read says which instant it asks about, e.g. as_of='2024-05-01' (SPEC 4.1)")
    b = bundle if isinstance(bundle, Bundle) else Bundle(bundle)
    t = _as_of(as_of)
    v = parse_instant(valid_at) if valid_at else t   # SPEC 4.1: valid_at defaults to as_of
    nodes = [r for r in b.nodes if _visible(r, t, v)]
    edges = [r for r in b.edges if _visible(r, t, v)]
    res = [r for r in b.resolutions if _visible(r, t, v)]

    # SPEC 4.3: when several visible edges replace one block, the latest asserted wins (ties by source id).
    # A successor whose applies_if is not among the block's own replaces it only for some cases: superseded_for.
    into = {}
    for e in sorted(edges, key=lambda e: (e["asserted_at"], e["source_id"])):
        if e["edge_type"] == "SUPERSEDES":
            into.setdefault(e["target_id"], []).append(e)
    succ = {e["source_id"] for es in into.values() for e in es}
    src = {}   # the successor's row: the latest known by as_of (known_at, then valid_from)
    for r in sorted((r for r in b.nodes if r["known_at"] <= t and r["id"] in succ),
                    key=lambda r: (r["known_at"], r["valid_from"])):
        src[r["id"]] = r
    out = []
    for r in nodes:
        mine = conditions(r)
        whole = [e for e in into.get(r["id"], ()) if mine is not None and (s := conditions(src.get(e["source_id"], {}))) is not None and s <= mine]
        part = [e for e in into.get(r["id"], ()) if e not in whole]
        # _replaced_at: when the replacement took effect (the edge's valid_from), not when the successor was said
        row = {**r, "superseded_by": whole[-1]["source_id"], "_replaced_at": whole[-1]["valid_from"]} if whole else {**r, "superseded_by": None}
        if part:
            row["superseded_for"] = [{"by": e["source_id"], "applies_if": src.get(e["source_id"], {}).get("applies_if")} for e in part]
            row["_replaced_for"] = part
        out.append(row)
    nodes = out

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


def scan(bundle: BundleLike, as_of: Instant, valid_at: Instant | None = None) -> Scan:
    """Use for analytics: everything the bundle knew as of an instant, as Arrow tables (.nodes, .edges,
    .resolutions) plus the certificate of what was hidden. For an agent's prompt use context() instead."""
    nodes, edges, res, cert = visible(bundle, as_of, valid_at)
    return Scan(_table(nodes), _table(edges), _table(res), cert)
