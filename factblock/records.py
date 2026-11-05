"""Rows you already have (a CSV export, a JSONL log) in, a bundle out. No model: every clock comes
from your columns, so the dates are exactly the ones you gave.

    from_records(rows, known_at=None, backfill=False) -> {"manifest", "nodes", "edges", "resolutions"}
    write_bundle(result, out, append=True)                                      # bundle.py

A row is a statement or a verdict.

  statement  id?, statement (or text), asserted_at (or said_at), valid_from (or effective_from)?,
             valid_to (or effective_to, or due)?, known_at?, kind?, replaces?, based_on?, applies_if? (conditions=True), speaker?, source?, author?
  verdict    target, outcome, decided_at, known_at?, value?, resolver?, method?, evidence?

`due` is a deadline (kind commitment) or horizon (prediction); a date means through the end of that day.
`replaces` names the id (or ids, separated by ";") this statement replaces: a SUPERSEDES edge, said and
in force when the new statement is. `based_on` names what it rests on the same way: a DERIVED_FROM edge
(it also stays in payload). With `conditions=True`, `applies_if` (`state=CA;county=LA|Ventura;acquired_after=2025-01-19`)
becomes the node's conditions (SPEC 3.1) and also stays in payload. Any other column goes into payload. Empty cells count as absent.
known_at is when you learned the row: its own column, else `known_at=`, else the day it was said or
decided with `backfill=True`, else now. write_bundle declares one batch per known_at (SPEC 6)."""
from __future__ import annotations

import csv
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from .bundle import Instant, _iso, parse_instant

ALIASES = {"text": "statement", "said_at": "asserted_at", "effective_from": "valid_from", "effective_to": "valid_to", "due": "valid_to"}
NODE_KEYS = {"id", "kind", "statement", "asserted_at", "valid_from", "valid_to", "known_at", "author", "category", "fact_key", "fact_value"}
VERDICT_KEYS = {"target", "outcome", "decided_at", "known_at", "value", "resolver", "method", "criteria", "evidence"}


def applies_if(cell) -> list[dict]:
    """An applies_if cell as SPEC 3.1 conditions: `key=value`, `key=a|b` (any of), `key_after=date`, `key_before=date`,
    joined by ';'. A list (from JSONL) is taken as already structured."""
    if isinstance(cell, list):
        return cell
    out = []
    for c in filter(None, (c.strip() for c in str(cell).split(";"))):
        key, sep, want = c.partition("=")
        if not sep or not key:
            raise ValueError(f"applies_if {c!r}: write key=value, key=a|b, key_after=date or key_before=date")
        op = next((o for o in ("after", "before") if key.endswith("_" + o)), "eq")
        vals = want.split("|")
        out.append({"key": key.removesuffix("_" + op), "op": op, "value": vals if op == "eq" and len(vals) > 1 else want})
    return out


def read_records(path) -> list[dict]:
    """A .csv (header row) or .jsonl file as dicts."""
    path = Path(path)
    if path.suffix == ".csv":
        with path.open(newline="") as f:
            return list(csv.DictReader(f))
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def from_records(rows: Iterable[dict], *, known_at: Instant | None = None, backfill: bool = False,
                 namespace: str = "local", columns: dict[str, str] | None = None, conditions: bool = False) -> dict:
    """Use when you have structured rows, not prose: each row becomes one block (or one verdict) with the
    dates its columns give. Pass the result to write_bundle(result, out, append=True); read_records(path)
    reads a .csv or .jsonl into rows. `factblock import` on the command line does both.

    statement  id?, statement|text, asserted_at|said_at, valid_from|effective_from?, valid_to|effective_to|due?,
               known_at?, kind? (default claim), replaces? (id;id, writes SUPERSEDES), based_on? (id;id, writes DERIVED_FROM,
               kept in payload too); other columns go to payload
    verdict    target, outcome, decided_at, known_at?, value?, resolver?, method?, evidence? (url;url)

    known_at, when missing on a row: `known_at=` if given, else the row's asserted_at (or decided_at) with
    backfill=True, else now. `columns` renames your columns first, e.g. {"Claim": "statement", "Date": "said_at"}.
    `conditions=True` also reads an `applies_if` column (key=v;key=a|b;key_after=date;key_before=date) as the node's
    SPEC 3.1 conditions, kept in payload too. Off by default: an `applies_if` column used to be payload only, and as
    conditions a narrower `replaces` reads as superseded_for, not superseded_by (SPEC 4.3)."""
    now = datetime.now(timezone.utc)
    fallback = parse_instant(known_at) if known_at else None
    nodes, edges, resolutions = [], [], []

    def learned(r, said):
        k = r.get("known_at") or fallback or (said if backfill else now)
        return _iso(parse_instant(k))

    for i, raw in enumerate(rows):
        if columns:
            raw = {columns.get(k, k): v for k, v in raw.items()}
        r = {ALIASES.get(k, k): v for k, v in raw.items() if v not in (None, "")}
        if "due" in raw and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(raw["due"] or "")):   # "by 2026-04-30" holds through that day
            r["valid_to"] = _iso(parse_instant(raw["due"]) + timedelta(days=1, seconds=-1))
        if "target" in r:
            missing = [k for k in ("outcome", "decided_at") if k not in r]
            if missing:
                raise ValueError(f"row {i + 1}: a verdict (it has target) needs {' and '.join(missing)}")
            v = {"target_id": r["target"], "value": r.get("value", r["outcome"]),
                 **{k: r[k] for k in VERDICT_KEYS - {"target", "value", "evidence"} if k in r}}
            if r.get("evidence"):
                ev = r["evidence"]
                v["evidence"] = ev if isinstance(ev, list) else [{"url": u.strip()} for u in str(ev).split(";")]
            v["known_at"] = learned(r, r["decided_at"])
            resolutions.append(v)
            continue
        missing = [k for k in ("statement", "asserted_at") if k not in r]
        if missing:
            raise ValueError(f"row {i + 1}: a statement needs {' and '.join(missing)} (or text, said_at); "
                             f"a verdict needs target, outcome, decided_at. Got columns {sorted(raw)}")
        n = {k: r[k] for k in NODE_KEYS if k in r}
        n.setdefault("id", uuid.uuid4().hex[:8]); n.setdefault("kind", "claim")
        n.setdefault("valid_from", n["asserted_at"]); n.setdefault("valid_to", None)
        n["known_at"] = learned(r, n["asserted_at"])
        # Later: `factblock import --conditions`, once a CLI user needs applies_if from a CSV
        if conditions and r.get("applies_if"):
            n["applies_if"] = applies_if(r["applies_if"])
        payload = {k: v for k, v in r.items() if k not in NODE_KEYS and k != "replaces"}
        if payload:
            n["payload"] = payload
        nodes.append(n)
        for col, etype in (("replaces", "SUPERSEDES"), ("based_on", "DERIVED_FROM")):
            for old in str(r.get(col, "")).split(";"):
                if old.strip():
                    edges.append({"source_id": n["id"], "target_id": old.strip(), "edge_type": etype,
                                  "asserted_at": n["asserted_at"], "valid_from": n["valid_from"], "valid_to": None, "known_at": n["known_at"]})

    manifest = {"factblock_version": "1.0-draft.1", "namespace": namespace, "exported_as_of": _iso(now)}
    return {"manifest": manifest, "nodes": nodes, "edges": edges, "resolutions": resolutions,
            "summary": {"blocks": len(nodes), "replaced": sum(e["edge_type"] == "SUPERSEDES" for e in edges), "verdicts": len(resolutions)}}
