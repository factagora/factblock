"""Graphiti (Zep) graph -> FactBlock bundle. The second implementation of the format:
it reads Graphiti's own objects, not tckg, and depends on nothing but the duck-typed
attributes below, so it runs against any Graphiti backend (Neo4j, FalkorDB, Kuzu).

Mapping (SPEC.md 3; tckg's memory/tckg_driver is the reverse direction):
  group_id                 -> space
  EpisodicNode             -> node kind=episode   (statement=name, asserted_at=valid_at)
  EntityNode               -> node kind=entity    (statement=name)
  EntityEdge (a fact)      -> node kind=claim     (statement=fact, valid=[valid_at, invalid_at) when
                              invalid_at was known at created_at; see "Invalidation" below)
                              + claim MENTIONS source entity, claim MENTIONS target entity
                              + claim DERIVED_FROM each episode it came from
  EpisodicEdge             -> edge episode MENTIONS entity
  created_at               -> known_at, attested by one backfill batch per distinct created_at:
                              Graphiti stamps created_at itself, so it is self-reported (SPEC 6, 9)
Invalidation: Graphiti closes a fact in place, setting invalid_at and expired_at (when it
learned the fact had ended) on the old edge. Writing valid_to = invalid_at on a row known at
created_at would hide, from every read between created_at and expired_at, a fact the store
still believed then. So a fact with expired_at becomes two rows: the original, open, known at
created_at; and a closed copy `<uuid>~closed` known at expired_at, which SUPERSEDES it.
Embeddings are not exported: the bundle cannot name the model (declarations.embedding is null).
"""
import json
from datetime import datetime, timezone
from pathlib import Path

LEDGER = "factblock-graphiti-adapter/0.1"


def _iso(d):
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).isoformat()


def _enum(v):
    return getattr(v, "value", v)


def bundle_from_graphiti(entities, episodes, facts, episodic_edges, exported_at=None) -> dict:
    """Returns {"manifest", "nodes", "edges"} as plain dicts; write_bundle() puts them on disk."""
    exported_at = _iso(exported_at or datetime.now(timezone.utc))
    # Batches are numbered in time order, whatever order the store returned rows in,
    # so an importer that applies them by number applies them chronologically and
    # never sees an edge before its endpoints.
    instants = sorted({_iso(x.created_at) for group in (entities, episodes, facts, episodic_edges) for x in group}
                      | {_iso(f.expired_at) for f in facts if getattr(f, "expired_at", None)})
    batches = {k: f"graphiti-{i + 1}" for i, k in enumerate(instants)}

    def batch_for(created_at):
        return batches[_iso(created_at)]

    def stamp(created_at):
        return {"known_at": _iso(created_at), "attestation": {"ledger": LEDGER, "batch": batch_for(created_at)}}

    nodes, edges, spaces, closing = [], [], set(), []
    ids = set()
    for e in episodes:
        spaces.add(e.group_id); ids.add(e.uuid)
        nodes.append({"id": e.uuid, "kind": "episode", "space": e.group_id, "statement": e.name,
                      "payload": {"source": _enum(e.source), "source_description": e.source_description,
                                  "content": e.content, "labels": list(getattr(e, "labels", []) or [])},
                      "asserted_at": _iso(e.valid_at), "valid_from": _iso(e.valid_at), "valid_to": None, **stamp(e.created_at)})
    for n in entities:
        spaces.add(n.group_id); ids.add(n.uuid)
        nodes.append({"id": n.uuid, "kind": "entity", "space": n.group_id, "statement": n.name,
                      "payload": {"labels": list(getattr(n, "labels", []) or []), "summary": getattr(n, "summary", "") or "",
                                  "attributes": dict(getattr(n, "attributes", {}) or {})},
                      "asserted_at": _iso(n.created_at), "valid_from": _iso(n.created_at), "valid_to": None, **stamp(n.created_at)})
    seen_edges = set()

    def edge(src, dst, typ, when, created_at):
        key = (src, dst, typ)
        if key in seen_edges or src not in ids or dst not in ids:
            return
        seen_edges.add(key)
        edges.append({"source_id": src, "target_id": dst, "edge_type": typ,
                      "asserted_at": _iso(when), "valid_from": _iso(when), "valid_to": None, **stamp(created_at)})

    for f in facts:
        spaces.add(f.group_id); ids.add(f.uuid)
        start = f.valid_at or f.created_at
        end = f.invalid_at if (f.invalid_at and start and f.invalid_at > start) else None
        payload = {"name": f.name, "episodes": list(f.episodes or []), "attributes": dict(getattr(f, "attributes", {}) or {})}
        if getattr(f, "expired_at", None):
            payload["graphiti_expired_at"] = _iso(f.expired_at)
        if f.invalid_at and end is None:
            payload["graphiti_invalid_at"] = _iso(f.invalid_at)     # kept, not applied: it did not follow valid_at
        expired = getattr(f, "expired_at", None)
        claim = {"id": f.uuid, "kind": "claim", "space": f.group_id, "statement": f.fact, "payload": payload,
                 "asserted_at": _iso(start), "valid_from": _iso(start), "valid_to": None if expired else _iso(end), **stamp(f.created_at)}
        nodes.append(claim)
        if expired and end:   # learned at expired_at that it had ended: a new row then, not a rewrite of the old one
            closed = f"{f.uuid}~closed"
            ids.add(closed)
            nodes.append({**claim, "id": closed, "valid_to": _iso(end), **stamp(expired)})
            closing.append((closed, f.uuid, expired))
    for f in facts:
        start = f.valid_at or f.created_at
        edge(f.uuid, f.source_node_uuid, "MENTIONS", start, f.created_at)
        edge(f.uuid, f.target_node_uuid, "MENTIONS", start, f.created_at)
        for ep in f.episodes or []:
            edge(f.uuid, ep, "DERIVED_FROM", start, f.created_at)
    for x in episodic_edges:
        edge(x.source_node_uuid, x.target_node_uuid, "MENTIONS", x.created_at, x.created_at)
    for closed, original, expired in closing:
        edge(closed, original, "SUPERSEDES", expired, expired)

    manifest = {
        "factblock_version": "1.0-draft.1",
        "namespace": "graphiti/" + ",".join(sorted(spaces)),
        "source": LEDGER,
        "exported_as_of": exported_at,
        "tables": {"nodes": "nodes.jsonl", "edges": "edges.jsonl"},
        "declarations": {
            "facts": [],
            "backfills": [{"batch": b, "declared_known_at": k, "reason": "Graphiti created_at, self-reported by the source store",
                           "declared_by": "process:" + LEDGER, "captured_at": exported_at} for k, b in batches.items()],
            "edge_types": [], "embedding": None},
    }
    return {"manifest": manifest, "nodes": nodes, "edges": edges}


from ..bundle import write_bundle  # noqa: E402,F401  (kept here for callers that imported it from the adapter)
