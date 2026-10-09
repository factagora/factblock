"""Three views of a FactBlock bundle, computed in DuckDB and rendered anywhere.

    con, pq = connect("samples/cramer")                 # Parquet copy + the macro pack (duckdb/factblock.sql)
    v = stance(con, pq, "SPY", as_of="2026-09-10")      # how a view changed over time
    v = evidence(con, pq, "fdc79a63b9b44a7f", as_of=...)  # what one statement rests on, and what it led to
    v = status(con, pq, as_of=...)                      # how many calls per subject are open, settled, replaced
    pick("Why was he bullish in March?")                # -> "evidence": which view a question needs

Every view is a plain dict, the same for a notebook, a chat answer or a web page:

    {"view", "title", "as_of", "rows", "spec"}

`rows` has one entry per mark on the chart, each carrying the FactBlock id(s) and the source URL behind
it, so any point can be traced back to the recording. `spec` is a Vega-Lite v5 spec over those rows:
Jupyter renders it as is, a web page passes it to vega-embed, a chat turns it into a PNG (vl-convert).
Nothing here renders; that is the caller's choice.

Links between statements are the speaker's own (`recorded`): a CAUSES edge says he said A causes B,
not that it does. Verdicts are the only checked part (here: the sign of the price move at the horizon)."""
import tempfile
from pathlib import Path

import duckdb

import factblock

MACROS = Path(__file__).resolve().parents[2] / "duckdb" / "factblock.sql"

# status palette (fixed roles, always shown with a label): settled true, settled false, no verdict yet, replaced
STATUS = {"came true": "#0ca30c", "did not": "#d03b3b", "no verdict": "#8c8b85", "replaced": "#b8b7af"}
FAMILY = {"causal": "#2a78d6", "argumentative": "#eb6834", "temporal": "#1baf7a"}   # categorical slots 1-3
FAMILY_OF = {"CAUSES": "causal", "CONTRIBUTING_FACTOR": "causal", "TRIGGERS": "causal", "PREVENTS": "causal",
             "SUPPORTS": "argumentative", "CONTRADICTS": "argumentative", "QUALIFIES": "argumentative",
             "SUPERSEDES": "temporal", "CONCURRENT_SIGNAL": "temporal", "RESTATES": "temporal"}
CONFIG = {"background": "#fcfcfb", "font": "Inter, system-ui, sans-serif",
          "axis": {"labelColor": "#52514e", "titleColor": "#52514e", "gridColor": "#ecebe7", "domainColor": "#c3c2b7", "tickColor": "#c3c2b7"},
          "legend": {"labelColor": "#52514e", "titleColor": "#52514e"},
          "title": {"color": "#0b0b0b", "subtitleColor": "#52514e", "anchor": "start", "fontSize": 15, "subtitleFontSize": 12},
          "view": {"stroke": None}}


def connect(bundle):
    """A DuckDB connection with the macro pack loaded, and the bundle's Parquet folder (written if it is JSONL)."""
    bundle = Path(bundle)
    pq = bundle if (bundle / "nodes.parquet").exists() else factblock.write_parquet(bundle, tempfile.mkdtemp(prefix="factblock-"))
    con = duckdb.connect()
    con.execute(MACROS.read_text())
    return con, str(pq)


def _rows(con, sql, params):
    cur = con.execute(sql, params)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _day(d):
    return f"factblock_day('{d}')" if len(str(d)) == 10 else f"TIMESTAMPTZ '{d}'"


def stance(con, pq, about, as_of):
    """Every call about `about` (payload.asset) said and known by as_of: up or down, and what became of it."""
    t = _day(as_of)
    rows = _rows(con, f"""
        WITH n AS (SELECT * FROM read_parquet(? || '/nodes.parquet')
                    WHERE known_at <= {t} AND kind = 'prediction' AND json_extract_string(payload, '$.asset') = ?
                      AND json_extract_string(payload, '$.direction') IN ('up', 'down')),
             s AS (SELECT target_id, min(valid_from) AS replaced_at FROM read_parquet(? || '/edges.parquet')
                    WHERE edge_type = 'SUPERSEDES' AND known_at <= {t} GROUP BY 1)
        SELECT n.id, n.asserted_at::DATE AS said, json_extract_string(n.payload, '$.direction') AS direction, n.statement,
               json_extract_string(n.payload, '$.source.url') AS url, v.outcome, v.decided_at::DATE AS decided, s.replaced_at::DATE AS replaced
          FROM n LEFT JOIN factblock_verdicts(?, {t}) v ON v.target_id = n.id LEFT JOIN s ON s.target_id = n.id
         ORDER BY n.asserted_at""", [pq, about, pq, pq])
    for r in rows:
        r["status"] = {"came_true": "came true", "did_not": "did not"}.get(r["outcome"]) or ("replaced" if r["replaced"] else "no verdict")
        r["said"], r["decided"], r["replaced"] = (str(x) if x else None for x in (r["said"], r["decided"], r["replaced"]))
    spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json", "config": CONFIG, "width": 760, "height": 170,
        "title": {"text": f"Calls on {about}, as known on {str(as_of)[:10]}",
                  "subtitle": "Each mark is one statement: up or down when it was said, coloured by what became of it. Click a mark for the recording."},
        "data": {"values": rows},
        "mark": {"type": "point", "filled": True, "size": 110, "opacity": 1, "stroke": "#fcfcfb", "strokeWidth": 2, "cursor": "pointer"},
        "encoding": {
            "x": {"field": "said", "type": "temporal", "title": None, "axis": {"format": "%b %Y", "tickCount": 8}},
            "y": {"field": "direction", "type": "nominal", "title": None, "sort": ["up", "down"], "axis": {"labelFontSize": 13}},
            "yOffset": {"field": "status", "type": "nominal", "sort": list(STATUS)},
            "color": {"field": "status", "type": "nominal", "title": "What became of it",
                      "scale": {"domain": list(STATUS), "range": list(STATUS.values())}},
            "shape": {"field": "status", "type": "nominal", "title": "What became of it", "scale": {"domain": list(STATUS), "range": ["triangle-up", "cross", "circle", "square"]}},
            "href": {"field": "url"},
            "tooltip": [{"field": "said", "type": "temporal", "title": "said"}, {"field": "statement"}, {"field": "status"},
                        {"field": "decided", "title": "verdict on"}, {"field": "replaced", "title": "replaced on"}, {"field": "id", "title": "FactBlock id"}, {"field": "url", "title": "source"}],
        },
    }
    return {"view": "stance", "title": spec["title"]["text"], "as_of": str(as_of), "rows": rows, "spec": spec}


def evidence(con, pq, block_id, as_of):
    """One statement and the statements linked to it, as known by as_of: what it rests on (left), what it
    led to or was replaced by (right). Every link is recorded, as the speaker drew it, and labelled so."""
    t = _day(as_of)
    links = _rows(con, f"""
        SELECT e.source_id, e.target_id, e.edge_type FROM factblock_edges(?, {t}) e
         WHERE (e.source_id = ? OR e.target_id = ?) AND e.edge_type <> 'MENTIONS'""", [pq, block_id, block_id])
    ids = {block_id} | {x for l in links for x in (l["source_id"], l["target_id"])}
    nodes = {r["id"]: r for r in _rows(con, f"""
        SELECT n.id, n.asserted_at::DATE::VARCHAR AS said, n.statement, json_extract_string(n.payload, '$.source.url') AS url, v.outcome
          FROM read_parquet(? || '/nodes.parquet') n LEFT JOIN factblock_verdicts(?, {t}) v ON v.target_id = n.id
         WHERE n.known_at <= {t} AND list_contains(?, n.id)""", [pq, pq, sorted(ids)])}
    side = {block_id: 0}
    for l in links:   # the rest of the chain on the left, consequences and successors on the right
        other, incoming = (l["source_id"], True) if l["target_id"] == block_id else (l["target_id"], False)
        right = (not incoming and l["edge_type"] != "SUPERSEDES") or (incoming and l["edge_type"] == "SUPERSEDES")
        side[other] = 1 if right else -1
        l.update(family=FAMILY_OF.get(l["edge_type"], "general"), basis="recorded by the speaker, not verified", other=other)
    for s in (-1, 1):
        col = sorted((i for i in side if side[i] == s), key=lambda i: nodes[i]["said"])
        for k, i in enumerate(col):
            nodes[i]["x"], nodes[i]["y"] = s, k - (len(col) - 1) / 2
    nodes[block_id].update(x=0, y=0)
    for n in nodes.values():
        n["role"] = {0: "subject", -1: "before", 1: "after"}[side[n["id"]]]
        n["label"] = (n["statement"][:58] + "…") if len(n["statement"]) > 60 else n["statement"]
        n["status"] = {"came_true": "came true", "did_not": "did not"}.get(n["outcome"], "no verdict")
    for l in links:
        a, b = nodes[l["source_id"]], nodes[l["target_id"]]
        l.update(x=a["x"], y=a["y"], x2=b["x"], y2=b["y"])
    rows = list(nodes.values())
    xs = {"type": "quantitative", "scale": {"domain": [-1.6, 1.6]}, "axis": None}
    ys = {"type": "quantitative", "scale": {"domain": [min(n["y"] for n in rows) - 0.8, max(n["y"] for n in rows) + 0.8]}, "axis": None}
    spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json", "config": CONFIG, "width": 760, "height": 90 + 70 * max(1, len(rows) // 2),
        "title": {"text": f"\u201c{nodes[block_id]['label']}\u201d: what it rests on, as known on {str(as_of)[:10]}",
                  "subtitle": "Links are the speaker's own claims (recorded, not verified). Verdicts are checked against prices."},
        "layer": [
            {"data": {"values": links}, "mark": {"type": "rule", "strokeWidth": 2},
             "encoding": {"x": {"field": "x", **xs}, "y": {"field": "y", **ys}, "x2": {"field": "x2"}, "y2": {"field": "y2"},
                          "color": {"field": "family", "type": "nominal", "title": "Recorded link",
                                    "scale": {"domain": list(FAMILY), "range": list(FAMILY.values())}},
                          "tooltip": [{"field": "edge_type", "title": "link"}, {"field": "source_id", "title": "from"}, {"field": "target_id", "title": "to"}, {"field": "basis"}]}},
            {"data": {"values": rows}, "mark": {"type": "point", "filled": True, "opacity": 1, "size": 160, "stroke": "#fcfcfb", "strokeWidth": 2, "cursor": "pointer"},
             "encoding": {"x": {"field": "x", **xs}, "y": {"field": "y", **ys}, "href": {"field": "url"},
                          "color": {"field": "status", "type": "nominal", "title": "Verdict",
                                    "scale": {"domain": ["came true", "did not", "no verdict"], "range": [STATUS["came true"], STATUS["did not"], "#52514e"]}},
                          "tooltip": [{"field": "said"}, {"field": "statement"}, {"field": "status", "title": "verdict"}, {"field": "id", "title": "FactBlock id"}, {"field": "url", "title": "source"}]}},
            {"data": {"values": rows}, "mark": {"type": "text", "dy": -16, "fontSize": 11, "color": "#0b0b0b", "limit": 230},
             "encoding": {"x": {"field": "x", **xs}, "y": {"field": "y", **ys}, "text": {"field": "label"}}},
            {"data": {"values": rows}, "mark": {"type": "text", "dy": 18, "fontSize": 10, "color": "#52514e"},
             "encoding": {"x": {"field": "x", **xs}, "y": {"field": "y", **ys}, "text": {"field": "said"}}},
        ],
        "resolve": {"scale": {"color": "independent"}},
    }
    return {"view": "evidence", "title": spec["title"]["text"], "as_of": str(as_of), "rows": rows, "links": links, "spec": spec}


def status(con, pq, as_of, top=10):
    """Calls known by as_of per subject (payload.asset), split by what became of them: came true, did not,
    no verdict yet, replaced. The subjects with the most calls, each bar segment with the ids behind it."""
    t = _day(as_of)
    rows = _rows(con, f"""
        WITH n AS (SELECT id, json_extract_string(payload, '$.asset') AS subject FROM read_parquet(? || '/nodes.parquet')
                    WHERE known_at <= {t} AND kind = 'prediction' AND json_extract_string(payload, '$.asset') IS NOT NULL),
             s AS (SELECT DISTINCT target_id FROM read_parquet(? || '/edges.parquet') WHERE edge_type = 'SUPERSEDES' AND known_at <= {t}),
             c AS (SELECT n.subject, n.id, CASE v.outcome WHEN 'came_true' THEN 'came true' WHEN 'did_not' THEN 'did not'
                          ELSE CASE WHEN s.target_id IS NOT NULL THEN 'replaced' ELSE 'no verdict' END END AS status
                     FROM n LEFT JOIN factblock_verdicts(?, {t}) v ON v.target_id = n.id LEFT JOIN s ON s.target_id = n.id),
             top AS (SELECT subject, count(*) AS total FROM c GROUP BY 1 ORDER BY total DESC, subject LIMIT {int(top)})
        SELECT c.subject, top.total, c.status, count(*) AS n, list(c.id ORDER BY c.id) AS ids
          FROM c JOIN top USING (subject) GROUP BY ALL ORDER BY top.total DESC, c.subject""", [pq, pq, pq])
    order = list(STATUS)
    spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json", "config": CONFIG, "width": 640, "height": 26 * top,
        "title": {"text": f"Calls per subject, as known on {str(as_of)[:10]}",
                  "subtitle": "Settled by the price move at each call's horizon. No verdict: not settled yet, or no horizon. Replaced: a later call superseded it."},
        "data": {"values": rows},
        "transform": [{"calculate": f"indexof({order}, datum.status)", "as": "o"}],
        "mark": {"type": "bar", "stroke": "#fcfcfb", "strokeWidth": 2, "cornerRadiusEnd": 0},
        "encoding": {
            "y": {"field": "subject", "type": "nominal", "title": None, "sort": {"field": "total", "order": "descending"}},
            "x": {"field": "n", "type": "quantitative", "title": "calls", "stack": "zero"},
            "order": {"field": "o"},
            "color": {"field": "status", "type": "nominal", "title": "What became of it", "scale": {"domain": order, "range": list(STATUS.values())}},
            "tooltip": [{"field": "subject"}, {"field": "status"}, {"field": "n", "title": "calls"}, {"field": "ids", "title": "FactBlock ids"}],
        },
    }
    return {"view": "status", "title": spec["title"]["text"], "as_of": str(as_of), "rows": rows, "spec": spec}


def pick(question):
    """Which view a question needs: why/because/evidence -> evidence; change/when/over time -> stance; else status."""
    q = question.lower()
    if any(w in q for w in ("why", "because", "evidence", "based on", "reason", "근거", "이유", "왜")):
        return "evidence"
    if any(w in q for w in ("change", "changed", "when", "over time", "flip", "turn", "변화", "바뀌", "언제")):
        return "stance"
    return "status"
