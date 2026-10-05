"""SPEC 4.5: the chain behind one block, as of an instant. Mirrors tckg.why(): a walk from the
block over causal, argumentative and temporal edges in both directions, every hop known at
`as_of` and in force at `valid_at`. The role names which end of the edge the block sits at."""
from collections import deque

from .bundle import Bundle
from .scan import scan
from .validate import CORE_FAMILY

WALKED = {"causal", "argumentative", "temporal"}
#        edge_type: (role of the node at the source, role of the node at the target)
ROLES = {"CAUSES": ("cause", "effect"), "CONTRIBUTING_FACTOR": ("contributing_cause", "contributed_effect"),
         "TRIGGERS": ("trigger", "triggered"), "PREVENTS": ("preventer", "prevented"),
         "SUPPORTS": ("support", "supported"), "CONTRADICTS": ("contradiction", "contradicted"),
         "QUALIFIES": ("qualification", "qualified"), "SUPERSEDES": ("successor", "predecessor"),
         "RESTATES": ("restatement", "restated"), "CONCURRENT_SIGNAL": ("concurrent", "concurrent")}


def why(bundle, node_id, as_of, valid_at=None, depth=3) -> dict:
    b = bundle if isinstance(bundle, Bundle) else Bundle(bundle)
    s = scan(b, as_of, valid_at)
    out = {"root": node_id, "as_of": s.certificate["as_of"], "valid_at": s.certificate["valid_at"], "chain": [], "certificate": s.certificate}
    nodes = {r["id"]: r for r in s.nodes.to_pylist()}
    if node_id not in nodes:
        out["reason"] = "not_yet" if any(r["id"] == node_id for r in b.nodes) else "absent"
        return out

    families = {**CORE_FAMILY, **b.edge_types}
    by_node = {}
    for e in s.edges.to_pylist():
        if families.get(e["edge_type"]) in WALKED:
            by_node.setdefault(e["source_id"], []).append(e)
            by_node.setdefault(e["target_id"], []).append(e)

    def row(nid, d, path, via=None, role="subject"):
        n = nodes[nid]
        return {"id": nid, "kind": n["kind"], "statement": n.get("statement"), "asserted_at": n["asserted_at"],
                "depth": d, "role": role, "path": path, "via": via and {k: via[k] for k in ("source_id", "target_id", "edge_type")}}

    seen = {node_id}
    chain = [row(node_id, 0, [node_id])]
    queue = deque([(node_id, 0, [node_id])])
    while queue:
        cur, d, path = queue.popleft()
        if d == depth:
            continue
        for e in by_node.get(cur, []):
            at_source = e["source_id"] != cur     # the neighbour sits at the source end
            nxt = e["source_id"] if at_source else e["target_id"]
            if nxt in seen or nxt not in nodes:
                continue
            seen.add(nxt)
            role = ROLES.get(e["edge_type"], (e["edge_type"].lower(), e["edge_type"].lower()))[0 if at_source else 1]
            chain.append(row(nxt, d + 1, path + [nxt], e, role))
            queue.append((nxt, d + 1, path + [nxt]))
    out["chain"] = sorted(chain, key=lambda r: (r["asserted_at"], r["depth"], r["id"]))
    return out
