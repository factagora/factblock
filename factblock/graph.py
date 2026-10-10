"""Graphs: what one statement rests on and what came of it, as known on a given day.

    g = factblock.graph("brain/", "fdc79a63b9b44a7f", as_of="2025-06-30")
    g                                   # in Jupyter: the chart
    g.nodes, g.edges                    # the rows behind it, each with its block id and source
    g.save("why.html")                  # .html needs nothing; .png and .svg need vl-convert-python
    g.to_mcp()                          # a tool result that MCP Apps hosts draw inline (mcp_app_html)

One row per statement, written in full beside a narrow column of dots: what the statement rests on (causes,
supports, the call it replaced) above it, the statement itself in bold, what came of it (effects, what it supported,
the call that replaced it) below, each group in the order things were said. An arrow is a link the speaker drew,
from source to target; a dot is coloured by what became of the statement. The walk is why(): links and verdicts
learned after as_of are not drawn. Rows keep their full width, so it reads in a narrow chat column.

nodes and edges use the field names a graph renderer takes as they are ({id, label, type, when, resolution} and
{id, from, to, label}), plus the FactBlock fields (role, status, source, history). Versioned as factblock.graph/v1
(schemas/graph.v1.schema.json)."""
from __future__ import annotations

from .bundle import Bundle, BundleLike, Instant, parse_instant
from .scan import visible
from .timeline import LEGEND_BELOW, Chart, _day, _short, _status, timeline
from .validate import CORE_FAMILY
from .why import WALKED, why

SCHEMA = "factblock.graph/v1"
FAMILY = {"causal": "#d9822b", "argumentative": "#7b61c9", "temporal": "#8c8b85"}   # not green or red: those are verdicts
RESOLUTION = {"right": "correct", "wrong": "wrong", "mixed": "ambiguous"}            # the words graph renderers use
# roles that put a statement downstream of the one it links to; every other role is upstream (what it rests on)
DOWN = {"effect", "contributed_effect", "triggered", "prevented", "supported", "contradicted", "qualified", "successor", "restatement"}
TIP = [{"field": "statement"}, {"field": "role"}, {"field": "status", "title": "as known"}, {"field": "history"},
       {"field": "id", "title": "FactBlock id"}, {"field": "source"}]


class Graph(Chart):
    """One statement and the statements linked to it, as known on as_of. Render with spec(), save(), or by leaving it
    as the last line of a Jupyter cell. nodes and edges are plain dicts for any other renderer."""

    def __init__(self, as_of, root, nodes, edges, certificate, title):
        self.as_of, self.root, self.nodes, self.edges, self.certificate, self.title = as_of, root, nodes, edges, certificate, title

    def to_dict(self) -> dict:
        """Everything behind the chart, JSON-ready: as_of, root, nodes, edges, certificate."""
        return {"schema": SCHEMA, "as_of": self.as_of, "root": self.root, "title": self.title,
                "nodes": self.nodes, "edges": self.edges, "certificate": self.certificate}

    def spec(self, width: int = 760) -> dict:
        """The Vega-Lite v5 spec: one row per statement on a time axis, links as arrows between them."""
        return {"$schema": "https://vega.github.io/schema/vega-lite/v5.json", **_spec(self, width)}

    def to_markdown(self) -> str:
        """The graph as text: the root, then each linked statement with its role, what became of it, and a source."""
        lines = [f"**{self.title}**", ""]
        for n in self.nodes:
            role = "this statement" if n["root"] else n["role"]
            src = f" [source]({n['source']})" if n["source"] else ""
            lines.append(f"- {n['when']} · {role}: {n['statement']} **{n['status']}**{src} `{n['id']}`")
        lines += ["", "_Links are the speaker's own (recorded, not verified). As known on "
                  f"{self.as_of[:10]}: nothing learned later is shown._"]
        return "\n".join(lines)

    def __repr__(self):
        return f"<Graph as of {self.as_of[:10]}: {len(self.nodes)} statements, {len(self.edges)} links around {self.root}>"


def graph(bundle: BundleLike, block_id: str, as_of: Instant, *, depth: int = 1, valid_at: Instant | None = None) -> Graph:
    """Use to show what one statement rests on and what came of it, as known on as_of: its causes, supports,
    contradictions and replacements up to `depth` links away (why()), each coloured by its outcome. Everything
    known by as_of is drawn, as timeline() does, including calls past their horizon; pass valid_at to draw only
    what was in force then. Raises ValueError when the block is not known at as_of."""
    b = bundle if isinstance(bundle, Bundle) else Bundle(bundle)
    w = why(b, block_id, as_of, valid_at, depth, in_force=valid_at is not None)
    if w.get("reason"):
        why_not = {"absent": "not in the bundle", "not_yet": "not known yet" if valid_at is None else "not known or not in force"}
        raise ValueError(f"{block_id} is {why_not[w['reason']]} as of {_day(w['as_of'])}")
    role = {r["id"]: r for r in w["chain"]}
    info = {c["id"]: c for c in timeline(b, as_of, ids=list(role), valid_at=valid_at).claims}
    families = {**CORE_FAMILY, **b.edge_types}
    t = parse_instant(w["as_of"])
    vis_edges = visible(b, as_of, valid_at)[1] if valid_at is not None else [e for e in b.edges if e["known_at"] <= t]
    links = [e for e in vis_edges if e["source_id"] in role and e["target_id"] in role and families.get(e["edge_type"]) in WALKED]

    side = {block_id: 0}
    for r in sorted(w["chain"], key=lambda r: r["depth"]):   # a statement sits on the side of the first link from the root
        if r["depth"]:
            first = role[r["path"][1]]
            side[r["id"]] = (1 if first["role"] in DOWN else -1) * r["depth"]
    # grouped by the first link from the root, groups in the order said; above the root a statement sits over the
    # one it leads into, below it under the one it came from, so a line never jumps over its own group
    def branch(i, sign):
        first = role[i]["path"][1]
        return (info[first]["said"], first, sign * role[i]["depth"], info[i]["said"], i)
    up = sorted((i for i in side if side[i] < 0), key=lambda i: branch(i, -1))
    down = sorted((i for i in side if side[i] > 0), key=lambda i: branch(i, 1))
    order = up + [block_id] + down
    rows = {i: k for k, i in enumerate(order)}
    nodes = []
    for i in order:
        c = info[i]
        nodes.append({"id": i, "label": _short(c["statement"], 70), "type": c["kind"].upper(), "when": c["said"],
                      "resolution": RESOLUTION.get(c["status"]), "kind": c["kind"], "statement": c["statement"],
                      "root": i == block_id, "role": "this statement" if i == block_id else role[i]["role"],
                      "depth": role[i]["depth"], "status": c["status"], "verdict": c["verdict"], "speaker": c["speaker"],
                      "source": c["source"], "history": c["history"], "lane": abs(side[i]), "row": rows[i]})
    at = {n["id"]: n for n in nodes}
    edges = []
    for e in links:
        a, z = at[e["source_id"]], at[e["target_id"]]
        edges.append({"id": f"{e['source_id']}>{e['edge_type']}>{e['target_id']}", "from": e["source_id"], "to": e["target_id"],
                      "label": e["edge_type"], "family": families.get(e["edge_type"]), "said": _day(e["asserted_at"]),
                      "x1": a["lane"], "y1": a["row"], "x2": z["lane"], "y2": z["row"], "xmid": (a["lane"] + z["lane"]) / 2,
                      "ymid": (a["row"] + z["row"]) / 2, "text": f"{_short(a['statement'], 50)} {e['edge_type']} {_short(z['statement'], 50)}"})
    root = at[block_id]
    title = f"What “{_short(root['statement'], 40)}” rests on"   # short: chart titles do not wrap
    return Graph(w["as_of"], block_id, nodes, edges, w["certificate"], title)


GUTTER = 22   # px per lane of dots; the statements take the rest of the width


def _spec(g, width):
    lanes = max(n["lane"] for n in g.nodes) + 1
    gutter = GUTTER * lanes
    x = {"type": "quantitative", "axis": None, "scale": {"domain": [-0.5, lanes - 0.5], "range": [0, gutter]}}
    y = {"type": "quantitative", "axis": None, "scale": {"domain": [-0.6, len(g.nodes) - 0.4], "reverse": True}}
    for n in g.nodes:
        n["text"] = f"{n['when']}  {n['statement']}"
    fam = {"field": "family", "type": "nominal", "title": "Link (recorded, not verified)",
           "scale": {"domain": list(FAMILY), "range": list(FAMILY.values())}}
    # the arrowhead turns with the drawn line
    angle = "atan2(scale('x', datum.x2) - scale('x', datum.x1), scale('y', datum.y1) - scale('y', datum.y2)) * 180 / PI"
    return {
        "config": LEGEND_BELOW,
        "title": {"text": g.title, "subtitle": [f"As known on {g.as_of[:10]}. Above: what it rests on;",
                                                "below: what came of it. Arrows are links the speaker drew;",
                                                "dots are coloured by what became of each statement."]},
        "width": width, "height": 30 * len(g.nodes),
        "layer": [
            {"data": {"values": g.edges}, "mark": {"type": "rule", "strokeWidth": 1.6},
             "encoding": {"x": {"field": "x1", **x}, "y": {"field": "y1", **y}, "x2": {"field": "x2"}, "y2": {"field": "y2"},
                          "color": fam, "strokeDash": {"condition": {"test": "datum.family === 'temporal'", "value": [4, 3]}, "value": [1, 0]},
                          "tooltip": [{"field": "text", "title": "link"}, {"field": "said", "title": "drawn"}]}},
            {"data": {"values": g.edges}, "mark": {"type": "point", "shape": "triangle", "filled": True, "size": 45, "opacity": 1, "angle": {"expr": angle}},
             "encoding": {"x": {"field": "xmid", **x}, "y": {"field": "ymid", **y}, "color": {**fam, "legend": None},
                          "tooltip": [{"field": "text", "title": "link"}]}},
            {"data": {"values": g.nodes}, "mark": {"type": "point", "filled": True, "opacity": 1, "stroke": "#0b0b0b", "cursor": "pointer"},
             "encoding": {"x": {"field": "lane", **x}, "y": {"field": "row", **y}, "color": _status(), "href": {"field": "source"}, "tooltip": TIP,
                          "size": {"condition": {"test": "datum.root", "value": 170}, "value": 80},
                          "strokeWidth": {"condition": {"test": "datum.root", "value": 2}, "value": 0}}},
            {"data": {"values": g.nodes}, "mark": {"type": "text", "align": "left", "baseline": "middle", "dx": gutter - GUTTER / 2 + 6,
                                                   "fontSize": 11.5, "color": "#0b0b0b", "cursor": "pointer", "limit": {"expr": f"width - {gutter + 8}"},
                                                   "fontWeight": {"expr": "datum.root ? 700 : 400"}},
             "encoding": {"x": {"datum": 0, **x}, "y": {"field": "row", **y}, "text": {"field": "text"}, "href": {"field": "source"}, "tooltip": TIP}},
        ],
        "resolve": {"scale": {"color": "independent"}},
    }
