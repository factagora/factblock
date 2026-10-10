"""SPEC 4.5: the chain behind one block, as of an instant. Mirrors tckg.why(): a walk from the
block over causal, argumentative and temporal edges in both directions, every hop known at
`as_of` and in force at `valid_at`. The role names which end of the edge the block sits at."""
from collections import deque

from .bundle import Bundle, BundleLike, Instant, parse_instant
from .scan import visible
from .validate import CORE_FAMILY

WALKED = {"causal", "argumentative", "temporal"}
#        edge_type: (role of the node at the source, role of the node at the target)
ROLES = {"CAUSES": ("cause", "effect"), "CONTRIBUTING_FACTOR": ("contributing_cause", "contributed_effect"),
         "TRIGGERS": ("trigger", "triggered"), "PREVENTS": ("preventer", "prevented"),
         "SUPPORTS": ("support", "supported"), "CONTRADICTS": ("contradiction", "contradicted"),
         "QUALIFIES": ("qualification", "qualified"), "SUPERSEDES": ("successor", "predecessor"),
         "RESTATES": ("restatement", "restated"), "CONCURRENT_SIGNAL": ("concurrent", "concurrent")}


def why(bundle: BundleLike, node_id: str, as_of: Instant, valid_at: Instant | None = None, depth: int = 3,
        in_force: bool = True) -> dict:
    """Use to explain one block: its causes, effects, supports, contradictions and replacements as known
    at `as_of`, each with a role and the path from the root. Empty chain with reason not_yet or absent.
    in_force=False walks every block and link known by as_of, in force at valid_at or not (a prediction past its
    horizon, a replaced call): the record as it stood, which is what graph() draws."""
    b = bundle if isinstance(bundle, Bundle) else Bundle(bundle)
    vis_nodes, vis_edges, _, bundle_cert = visible(b, as_of, valid_at)
    t, v = parse_instant(bundle_cert["as_of"]), parse_instant(bundle_cert["valid_at"])
    if not in_force:
        vis_nodes, vis_edges = [r for r in b.nodes if r["known_at"] <= t], [e for e in b.edges if e["known_at"] <= t]
    cert = {k: bundle_cert[k] for k in ("as_of", "read_at", "valid_at")}
    out = {"root": node_id, "as_of": cert["as_of"], "valid_at": cert["valid_at"], "chain": [], "certificate": cert}
    nodes = {r["id"]: r for r in vis_nodes}
    if node_id not in nodes:
        root = next((r for r in b.nodes if r["id"] == node_id), None)
        out["reason"] = "not_yet" if root else "absent"
        if root:   # the one block this walk hid is the root itself
            cert["masked" if root["known_at"] > t else "not_in_force"] = {"node": 1}
        return out

    families = {**CORE_FAMILY, **b.edge_types}
    shown = {id(e) for e in vis_edges}
    by_node = {}
    for e in b.edges:                      # every walked edge, so the certificate can count the hidden ones
        if families.get(e["edge_type"]) in WALKED:
            by_node.setdefault(e["source_id"], []).append(e)
            by_node.setdefault(e["target_id"], []).append(e)
    raw = {r["id"]: r for r in b.nodes}
    hidden = {"masked": {}, "not_in_force": {}}   # SPEC 4.5: the certificate covers this walk, not the bundle
    counted = set()

    def hide(kind, r, key):
        if key not in counted:
            counted.add(key)
            bucket = hidden["masked" if r["known_at"] > t else "not_in_force"]
            bucket[kind] = bucket.get(kind, 0) + 1

    def row(nid, d, path, via=None, role="subject"):
        n = nodes[nid]
        return {"id": nid, "kind": n["kind"], "statement": n.get("statement"), "asserted_at": n["asserted_at"],
                "depth": d, "role": role, "path": path, "via": via and {k: via[k] for k in ("source_id", "target_id", "edge_type")}}

    seen = {node_id}
    chain = [row(node_id, 0, [node_id])]
    queue = deque([(node_id, 0, [node_id])])
    batches = set()
    while queue:
        cur, d, path = queue.popleft()
        if d == depth:
            continue
        for e in by_node.get(cur, []):
            at_source = e["source_id"] != cur     # the neighbour sits at the source end
            nxt = e["source_id"] if at_source else e["target_id"]
            if id(e) not in shown:
                hide("edge", e, ("e", id(e)))
                continue
            if nxt not in nodes:
                if nxt in raw:
                    hide("node", raw[nxt], ("n", nxt))
                continue
            if nxt in seen:
                continue
            seen.add(nxt)
            if (e.get("attestation") or {}).get("batch"):
                batches.add(e["attestation"]["batch"])
            role = ROLES.get(e["edge_type"], (e["edge_type"].lower(), e["edge_type"].lower()))[0 if at_source else 1]
            chain.append(row(nxt, d + 1, path + [nxt], e, role))
            queue.append((nxt, d + 1, path + [nxt]))
    rows = sum(1 for nid in seen if (nodes[nid].get("attestation") or {}).get("batch"))
    batches |= {nodes[nid]["attestation"]["batch"] for nid in seen if (nodes[nid].get("attestation") or {}).get("batch")}
    for k in ("masked", "not_in_force"):
        if hidden[k]:
            cert[k] = hidden[k]
    if batches:
        cert["backfill"] = {"batches": len(batches), "rows": rows}
    out["chain"] = sorted(chain, key=lambda r: (r["asserted_at"], r["depth"], r["id"]))
    return out
