"""SPEC 9.1: the OKF projection. One concept document per node visible as of an instant, plus
index.md and log.md, in the Open Knowledge Format (markdown + YAML frontmatter, v0.2). Lossy by
design: OKF has one clock and untyped links, so edges become links with the relation in prose,
and the clocks OKF cannot hold ride under a `factblock:` key that a consumer may ignore."""
import json
from pathlib import Path

from .bundle import Bundle, parse_instant
from .scan import _as_of, _visible, scan

PROSE = {"CAUSES": "causes", "CONTRIBUTING_FACTOR": "contributes to", "TRIGGERS": "triggers", "PREVENTS": "prevents",
         "SUPPORTS": "supports", "CONTRADICTS": "contradicts", "QUALIFIES": "qualifies", "SUPERSEDES": "supersedes",
         "RESTATES": "restates", "CONCURRENT_SIGNAL": "occurs with", "DEPENDS_ON": "depends on", "DERIVED_FROM": "is derived from",
         "MENTIONS": "mentions"}


def _y(v):
    """A YAML scalar or flow collection. JSON is valid YAML, so json.dumps is the whole serializer."""
    return json.dumps(v, default=lambda d: d.isoformat())


def _doc(n, b, edges, verdicts):
    payload = n.get("payload") or {}
    fm = {"type": n["kind"], "title": n.get("statement") or n["id"], "resource": f"factblock:{b.manifest.get('namespace', '')}/{n['id']}"}
    if n.get("category"):
        fm["tags"] = [n["category"]]
    gen = {"at": n["asserted_at"]}
    if n.get("author"):
        gen["by"] = n["author"]
    fm["generated"] = gen
    if n.get("valid_to"):
        fm["stale_after"] = n["valid_to"]
    src = payload.get("source")
    if isinstance(src, dict) and src.get("url"):
        fm["sources"] = [{"id": "src", "resource": src["url"], **({"title": src["title"]} if src.get("title") else {})}]
    sup = [e["source_id"] for e in edges if e["edge_type"] == "SUPERSEDES" and e["target_id"] == n["id"]]
    pre = [e["target_id"] for e in edges if e["edge_type"] == "SUPERSEDES" and e["source_id"] == n["id"]]
    if sup:
        fm["superseded_by"] = [f"{x}.md" for x in sup]
    if pre:
        fm["supersedes"] = [f"{x}.md" for x in pre]
    fm["factblock"] = {"id": n["id"], "known_at": n["known_at"], "valid_from": n["valid_from"], "attestation": n.get("attestation"),
                       **({"speaker": payload["speaker"]} if payload.get("speaker") else {})}
    lines = ["---"] + [f"{k}: {_y(v)}" for k, v in fm.items()] + ["---", "", f"# {fm['title']}", ""]
    if payload.get("quote"):
        lines += [f"> {payload['quote']}", ""]
    rel = [e for e in edges if n["id"] in (e["source_id"], e["target_id"])]
    if rel:
        lines += ["## Relations", ""]
        for e in sorted(rel, key=lambda e: (e["asserted_at"], e["edge_type"])):
            other = e["target_id"] if e["source_id"] == n["id"] else e["source_id"]
            verb = PROSE.get(e["edge_type"], e["edge_type"].lower().replace("_", " "))
            line = f"- This {verb} [{other}]({other}.md)" if e["source_id"] == n["id"] else f"- [{other}]({other}.md) {verb} this"
            extra = [x for x in (e.get("mechanism"), f"lag {e['lag']}" if e.get("lag") else None,
                                 f"confidence {e['confidence']}" if e.get("confidence") is not None else None) if x]
            lines.append(line + (f" ({'; '.join(extra)})" if extra else "") + f". Asserted {e['asserted_at'].date().isoformat()}.")
        lines.append("")
    mine = [r for r in verdicts if r["target_id"] == n["id"]]
    if mine:
        lines += ["## Verdicts", ""]
        for r in sorted(mine, key=lambda r: r["decided_at"]):
            lines.append(f"- {r.get('outcome') or _y(r.get('value'))}, decided {r['decided_at'].date().isoformat()}"
                         + (f" by {r['resolver']}" if r.get("resolver") else "") + (f" ({r['method']})" if r.get("method") else ""))
        lines.append("")
    return "\n".join(lines)


def to_okf(bundle, as_of, out, valid_at=None) -> Path:
    """Use to hand a bundle to people or agents that read markdown: one OKF concept document per visible block (SPEC 9.1)."""
    b = bundle if isinstance(bundle, Bundle) else Bundle(bundle)
    s = scan(b, as_of, valid_at)
    t = _as_of(as_of); v = parse_instant(valid_at) if valid_at else t
    nodes = [n for n in b.nodes if _visible(n, t, v)]
    ids = {n["id"] for n in nodes}
    edges = [e for e in b.edges if _visible(e, t, v) and e["source_id"] in ids and e["target_id"] in ids]
    verdicts = [r for r in b.resolutions if _visible(r, t, v) and r["target_id"] in ids]
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    for n in nodes:
        (out / f"{n['id']}.md").write_text(_doc(n, b, edges, verdicts))
    index = ["---", "okf_version: \"0.2\"", f"title: {_y(b.manifest.get('namespace', 'factblock'))}",
             f"description: {_y('FactBlock bundle projected to OKF as of ' + s.certificate['as_of'])}",
             f"generated: {_y({'by': 'factblock/okf', 'at': s.certificate['read_at']})}",
             f"factblock: {_y({'certificate': s.certificate})}", "---", "", f"# {b.manifest.get('namespace', 'factblock')}", ""]
    index += [f"- [{n.get('statement') or n['id']}]({n['id']}.md) ({n['kind']})" for n in sorted(nodes, key=lambda n: (n["asserted_at"], n["id"]))]
    (out / "index.md").write_text("\n".join(index) + "\n")
    events = [(n["known_at"], f"[{n['id']}]({n['id']}.md) learned: {n.get('statement') or n['id']} (asserted {n['asserted_at'].date().isoformat()})") for n in nodes]
    events += [(e["known_at"], f"[{e['source_id']}]({e['source_id']}.md) {PROSE.get(e['edge_type'], e['edge_type'])} [{e['target_id']}]({e['target_id']}.md)") for e in edges]
    events += [(r["known_at"], f"verdict on [{r['target_id']}]({r['target_id']}.md): {r.get('outcome') or _y(r.get('value'))}") for r in verdicts]
    log = ["# Log", "", "What the ledger learned, in the order it learned it (known_at).", ""]
    log += [f"- {k.isoformat()}: {text}" for k, text in sorted(events, key=lambda x: x[0])]
    (out / "log.md").write_text("\n".join(log) + "\n")
    return out
