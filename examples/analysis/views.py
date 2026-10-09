"""Views of a FactBlock bundle, computed in DuckDB and rendered anywhere.

Findings, each one a thing a table of statements cannot answer on its own:

    con, pq = connect("samples/cramer")      # Parquet copy + the macro pack (duckdb/factblock.sql)
    backtest(con, pq, as_of)                 # a selection rule run as of each call vs with hindsight (look-ahead bias)
    track_record(con, pq, as_of)             # his hit rate as it could be known each month (verdicts carry known_at)
    reversals(con, pq, as_of)                # did changing his mind help? (replaced calls are kept, not overwritten)
    reasons(con, pq, as_of)                  # were calls he gave reasons for more accurate? (links + verdicts)

and two drill-downs to the statements behind them:

    stance(con, pq, "SPY", as_of)            # every call on one subject, up or down, and what became of it
    evidence(con, pq, block_id, as_of)       # what one statement rests on, and what it led to
    pick("Why was he bullish in March?")     # -> "evidence": which view a question needs

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


HEADLINE = {**CONFIG, "title": {**CONFIG["title"], "fontSize": 17, "subtitleFontSize": 12.5, "subtitlePadding": 6, "offset": 14}}


STRATEGY = {"rule, picked with hindsight": "#eb6834", "every call": "#8c8b85", "rule, picked as of each call": "#2a78d6"}


def backtest(con, pq, as_of, threshold=0.5, min_settled=3):
    """Follow his calls (long on up, short on down, entry and exit as each verdict scores them) under one rule:
    only on subjects where his record is at least `threshold` over `min_settled` settled calls. The record is
    read two ways. As of each call: verdicts known before the call was made. With hindsight: every verdict known
    today, which is what a table of final outcomes gives. The running return per call is the equity curve."""
    t = _day(as_of)
    calls = _rows(con, f"""
        WITH c AS (SELECT n.id, n.asserted_at AS said, v.known_at AS settled, json_extract_string(n.payload, '$.asset') AS subject,
                          CASE json_extract_string(n.payload, '$.direction') WHEN 'up' THEN 1 ELSE -1 END
                            * (v.value->>'return')::DOUBLE AS pnl, v.outcome = 'came_true' AS hit
                     FROM read_parquet(? || '/nodes.parquet') n JOIN factblock_verdicts(?, {t}) v ON v.target_id = n.id
                    WHERE json_extract_string(n.payload, '$.direction') IN ('up', 'down') AND json_extract_string(n.payload, '$.asset') IS NOT NULL
                      AND (v.value->>'return') IS NOT NULL)
        SELECT c.id, c.settled::DATE::VARCHAR AS settled, c.subject, c.pnl,
               (SELECT count(*) FROM c q WHERE q.subject = c.subject AND q.settled < c.said) AS asof_n,
               (SELECT avg(q.hit::INT) FROM c q WHERE q.subject = c.subject AND q.settled < c.said) AS asof_rate,
               (SELECT count(*) FROM c q WHERE q.subject = c.subject AND q.id <> c.id) AS hind_n,
               (SELECT avg(q.hit::INT) FROM c q WHERE q.subject = c.subject AND q.id <> c.id) AS hind_rate
          FROM c ORDER BY c.settled, c.id""", [pq, pq])
    picks = {"every call": lambda c: True,
             "rule, picked as of each call": lambda c: c["asof_n"] >= min_settled and c["asof_rate"] >= threshold,
             "rule, picked with hindsight": lambda c: c["hind_n"] >= min_settled and c["hind_rate"] >= threshold}
    rows, summary = [], {}
    for name, keep in picks.items():
        total = n = 0
        for c in calls:
            if keep(c):
                total += c["pnl"]; n += 1
                rows.append({"day": c["settled"], "strategy": name, "per_call": total / n, "calls": n, "id": c["id"], "subject": c["subject"]})
        summary[name] = {"calls": n, "per_call": total / n if n else 0.0}
    rows = [r for r in rows if r["calls"] >= 20]   # a running average over a handful of calls is noise
    names = {k: f"{k}: {v['per_call']:+.1%} a call over {v['calls']} calls" for k, v in summary.items()}
    for r in rows:
        r["strategy"] = names[r["strategy"]]
    h, a, e = (summary[k] for k in ("rule, picked with hindsight", "rule, picked as of each call", "every call"))
    head = f"Following only his best subjects looks like {h['per_call']:+.1%} a call. Picked with what was known at the time, it makes {a['per_call']:+.1%}."
    x = {"field": "day", "type": "temporal", "title": "verdict date", "axis": {"format": "%b %Y", "tickCount": 8}}
    color = {"field": "strategy", "type": "nominal", "title": None, "scale": {"domain": [names[k] for k in STRATEGY], "range": list(STRATEGY.values())}}
    spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json", "config": HEADLINE, "width": 760, "height": 300,
        "title": {"text": head, "subtitle": [
            f"Rule: follow his calls only on subjects where at least {threshold:.0%} of his {min_settled}+ settled calls came true. Following every call makes {e['per_call']:+.1%}.",
            "The hindsight line reads his record from final outcomes, so it picks with verdicts that did not exist yet. FactBlock dates every",
            "verdict (known_at), so the rule can be run as it would have been: blue. Running average return per call (from the 20th call), long on up, short on down."]},
        "data": {"values": rows},
        "layer": [
            {"mark": {"type": "rule", "color": "#c3c2b7"}, "encoding": {"y": {"datum": 0}}},
            {"mark": {"type": "line", "strokeWidth": 2.5, "interpolate": "step-after"},
             "encoding": {"x": x, "y": {"field": "per_call", "type": "quantitative", "title": "average return per call so far", "axis": {"format": "+.0%"}},
                          "color": {**color, "legend": {"orient": "bottom", "direction": "vertical", "labelFontSize": 12.5, "labelLimit": 500}},
                          "tooltip": [{"field": "strategy"}, {"field": "day", "type": "temporal", "format": "%d %b %Y"}, {"field": "per_call", "format": "+.1%", "title": "per call so far"},
                                      {"field": "calls"}, {"field": "subject", "title": "last call on"}, {"field": "id", "title": "FactBlock id"}]}},
        ],
    }
    return {"view": "backtest", "title": head, "as_of": str(as_of), "rows": rows, "summary": summary, "spec": spec}


def track_record(con, pq, as_of):
    """His hit rate on the first of each month, read two ways. As it was known: only verdicts known by then
    (each verdict carries its own known_at, the day its horizon price settled). With hindsight: every call
    made by then, scored with today's verdicts, which is what a table of final outcomes gives a backtest.
    The gap is the verdicts that did not exist yet."""
    t = _day(as_of)
    rows = _rows(con, f"""
        WITH m AS (SELECT unnest(generate_series(DATE '2024-01-01', date_trunc('month', {t})::DATE, INTERVAL 1 MONTH))::DATE AS day),
             v AS (SELECT r.target_id, r.outcome, r.known_at, n.asserted_at FROM factblock_verdicts(?, {t}) r
                     JOIN read_parquet(? || '/nodes.parquet') n ON n.id = r.target_id)
        SELECT day::VARCHAR AS day,
               count(*) FILTER (WHERE v.known_at < day) AS known, avg((v.outcome = 'came_true')::INT) FILTER (WHERE v.known_at < day) AS known_rate,
               count(*) FILTER (WHERE v.asserted_at < day) AS hindsight, avg((v.outcome = 'came_true')::INT) FILTER (WHERE v.asserted_at < day) AS hindsight_rate
          FROM m, v GROUP BY day HAVING count(*) FILTER (WHERE v.known_at < day) >= 25 ORDER BY day""", [pq, pq])
    for r in rows:
        r["future"] = r["hindsight"] - r["known"]
    pick_ = max((r for r in rows if r["known"] >= 100), key=lambda r: abs(r["hindsight_rate"] - r["known_rate"]))
    lines = [{"day": r["day"], "series": k, "rate": r[f], "calls": r[n], "label": f"{r[f]:.0%} of {r[n]}" if r is pick_ else None}
             for r in rows for k, f, n in (("as it was known that day", "known_rate", "known"), ("with hindsight (a table of final outcomes)", "hindsight_rate", "hindsight"))]
    day = f"{int(pick_['day'][8:10])} {('Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec')[int(pick_['day'][5:7]) - 1]} {pick_['day'][:4]}"
    head = f"On {day} his record read {pick_['known_rate']:.0%}. A backtest on today's data says {pick_['hindsight_rate']:.0%} for that same day."
    series = {"as it was known that day": "#2a78d6", "with hindsight (a table of final outcomes)": "#eb6834"}
    x = {"field": "day", "type": "temporal", "title": None, "axis": {"format": "%b %Y", "tickCount": 8}}
    spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json", "config": HEADLINE,
        "title": {"text": head, "subtitle": [f"The backtest counted {pick_['future']} verdicts that did not exist yet. Share of his settled calls that came true, on the first of each month.",
                                             "FactBlock stores each verdict as a row with its own known_at, so the record replays as it stood. A table of final outcomes can only draw the orange line."]},
        "vconcat": [
            {"width": 760, "height": 230, "data": {"values": lines}, "layer": [
                {"mark": {"type": "rule", "strokeDash": [4, 4], "color": "#8c8b85"}, "encoding": {"y": {"datum": 0.5}}},
                {"mark": {"type": "line", "strokeWidth": 2.5, "point": {"filled": True, "size": 40}},
                 "encoding": {"x": x, "y": {"field": "rate", "type": "quantitative", "title": "calls right (dashed: coin flip)", "axis": {"format": ".0%"}, "scale": {"domain": [0.4, 0.6], "zero": False, "clamp": True}},
                              "color": {"field": "series", "type": "nominal", "title": None, "legend": {"orient": "top-right", "labelFontSize": 12, "labelLimit": 400, "direction": "vertical"},
                                        "scale": {"domain": list(series), "range": list(series.values())}},
                              "tooltip": [{"field": "day", "type": "temporal", "format": "%d %b %Y"}, {"field": "series"},
                                          {"field": "rate", "format": ".1%", "title": "right"}, {"field": "calls", "title": "settled calls"}]}},
                {"transform": [{"filter": "datum.label != null"}],
                 "mark": {"type": "text", "align": "left", "dx": 8, "fontSize": 13, "fontWeight": 600},
                 "encoding": {"x": x, "y": {"field": "rate", "type": "quantitative"}, "text": {"field": "label"},
                              "color": {"field": "series", "type": "nominal", "scale": {"domain": list(series), "range": list(series.values())}, "legend": None}}},
            ]},
            {"width": 760, "height": 80, "data": {"values": rows},
             "title": {"text": "Verdicts from the future: in the hindsight line, not yet known that day", "fontSize": 12, "fontWeight": 500, "color": "#52514e"},
             "mark": {"type": "bar", "color": "#eb6834", "opacity": 0.75, "cornerRadiusEnd": 2, "width": {"band": 0.6}},
             "encoding": {"x": {**x, "timeUnit": "yearmonth", "axis": None}, "y": {"field": "future", "type": "quantitative", "title": None, "axis": {"tickCount": 3}},
                          "tooltip": [{"field": "day", "type": "temporal", "format": "%d %b %Y"}, {"field": "future", "title": "verdicts not yet known"}]}},
        ],
    }
    return {"view": "track_record", "title": head, "as_of": str(as_of), "rows": rows, "spec": spec}


REVERSAL = {"fixed a wrong call": "#0ca30c", "broke a right call": "#d03b3b", "both right": "#8c8b85", "both wrong": "#b8b7af"}


def reversals(con, pq, as_of):
    """Every call he later replaced with the opposite call (a SUPERSEDES row from the new call to the old one),
    and, where both have a verdict by as_of, whether the reversal fixed a wrong call or broke a right one.
    Possible only because the replaced call is kept, not overwritten."""
    t = _day(as_of)
    rows = _rows(con, f"""
        WITH r AS (SELECT e.target_id AS old_id, e.source_id AS new_id, vo.outcome AS old_v, vn.outcome AS new_v
                     FROM read_parquet(? || '/edges.parquet') e
                     LEFT JOIN factblock_verdicts(?, {t}) vo ON vo.target_id = e.target_id
                     LEFT JOIN factblock_verdicts(?, {t}) vn ON vn.target_id = e.source_id
                    WHERE e.edge_type = 'SUPERSEDES' AND e.known_at <= {t})
        SELECT CASE WHEN old_v IS NULL OR new_v IS NULL THEN 'not both settled'
                    WHEN old_v = 'did_not' AND new_v = 'came_true' THEN 'fixed a wrong call'
                    WHEN old_v = 'came_true' AND new_v = 'did_not' THEN 'broke a right call'
                    WHEN old_v = 'came_true' THEN 'both right' ELSE 'both wrong' END AS outcome,
               count(*) AS n, list([old_id, new_id] ORDER BY old_id) AS pairs
          FROM r GROUP BY 1""", [pq, pq, pq])
    by = {r["outcome"]: r for r in rows}
    total = sum(r["n"] for r in rows)
    settled = [by.get(k, {"outcome": k, "n": 0, "pairs": []}) for k in REVERSAL]
    both = sum(r["n"] for r in settled)
    fixed, broke = (by.get(k, {"n": 0})["n"] for k in ("fixed a wrong call", "broke a right call"))
    head = f"He reversed himself {total} times. Where both calls were settled, {fixed} reversals fixed a wrong call and {broke} broke a right one."
    for r in settled:
        r["share"] = r["n"] / both if both else 0
    spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json", "config": HEADLINE, "width": 760, "height": 190,
        "title": {"text": head, "subtitle": [f"The {both} reversals where the old and the new call both have a verdict. Changing his mind did not change his accuracy.",
                                             "A store that overwrites keeps only the new call. FactBlock keeps both (the new one SUPERSEDES the old), so both can be scored."]},
        "data": {"values": settled},
        "layer": [
            {"mark": {"type": "bar", "cornerRadiusEnd": 3, "height": 30},
             "encoding": {"y": {"field": "outcome", "type": "nominal", "title": None, "sort": list(REVERSAL), "axis": {"labelFontSize": 13, "labelLimit": 220}},
                          "x": {"field": "n", "type": "quantitative", "title": "reversals"},
                          "color": {"field": "outcome", "type": "nominal", "legend": None, "scale": {"domain": list(REVERSAL), "range": list(REVERSAL.values())}},
                          "tooltip": [{"field": "outcome"}, {"field": "n", "title": "reversals"}, {"field": "pairs", "title": "[old, new] FactBlock ids"}]}},
            {"mark": {"type": "text", "align": "left", "dx": 6, "fontSize": 13, "fontWeight": 600, "color": "#0b0b0b"},
             "encoding": {"y": {"field": "outcome", "type": "nominal", "sort": list(REVERSAL)}, "x": {"field": "n", "type": "quantitative"}, "text": {"field": "n"}}},
        ],
    }
    return {"view": "reversals", "title": head, "as_of": str(as_of), "total": total, "rows": settled, "spec": spec}


def reasons(con, pq, as_of):
    """Settled calls split by whether he gave a reason for them: an incoming link he drew himself (CAUSES,
    CONTRIBUTING_FACTOR, TRIGGERS, SUPPORTS) known by as_of. The links are recorded, not verified; the outcome is."""
    t = _day(as_of)
    rows = _rows(con, f"""
        WITH c AS (SELECT n.id, v.outcome,
                          EXISTS (SELECT 1 FROM factblock_edges(?, {t}) e WHERE e.target_id = n.id
                                     AND e.edge_type IN ('CAUSES', 'CONTRIBUTING_FACTOR', 'TRIGGERS', 'SUPPORTS')) AS has_reason
                     FROM read_parquet(? || '/nodes.parquet') n JOIN factblock_verdicts(?, {t}) v ON v.target_id = n.id
                    WHERE n.known_at <= {t} AND n.kind = 'prediction')
        SELECT CASE WHEN has_reason THEN 'gave a reason' ELSE 'no reason given' END AS calls,
               count(*) AS settled, avg((outcome = 'came_true')::INT) AS hit_rate, list(id ORDER BY id) AS ids
          FROM c GROUP BY 1 ORDER BY 1""", [pq, pq, pq])
    a, b = (next(r for r in rows if r["calls"] == k) for k in ("gave a reason", "no reason given"))
    for r in rows:
        r["label"] = f"{r['hit_rate']:.0%} right, of {r['settled']}"
    head = f"Giving a reason did not make him more accurate: {a['hit_rate']:.0%} with a reason, {b['hit_rate']:.0%} without."
    spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json", "config": HEADLINE, "width": 760, "height": 130,
        "title": {"text": head, "subtitle": ["Settled calls, split by whether he linked a reason to them (CAUSES, SUPPORTS, ...). The links are his own, recorded,",
                                             "not verified; the outcome is checked against the price. Links and verdicts live in one bundle, so this is one join."]},
        "data": {"values": rows},
        "layer": [
            {"mark": {"type": "bar", "cornerRadiusEnd": 3, "height": 34, "color": "#2a78d6"},
             "encoding": {"y": {"field": "calls", "type": "nominal", "title": None, "axis": {"labelFontSize": 13}},
                          "x": {"field": "hit_rate", "type": "quantitative", "title": "right", "scale": {"domain": [0, 1]}, "axis": {"format": ".0%"}},
                          "tooltip": [{"field": "calls"}, {"field": "settled"}, {"field": "hit_rate", "format": ".1%", "title": "right"}]}},
            {"mark": {"type": "text", "align": "left", "dx": 6, "fontSize": 13, "fontWeight": 600, "color": "#0b0b0b"},
             "encoding": {"y": {"field": "calls", "type": "nominal"}, "x": {"field": "hit_rate", "type": "quantitative"}, "text": {"field": "label"}}},
            {"mark": {"type": "rule", "strokeDash": [4, 4], "color": "#8c8b85"}, "encoding": {"x": {"datum": 0.5}}},
            {"mark": {"type": "text", "dy": -78, "color": "#52514e", "fontSize": 11}, "encoding": {"x": {"datum": 0.5}, "text": {"value": "coin flip"}}},
        ],
    }
    return {"view": "reasons", "title": head, "as_of": str(as_of), "rows": rows, "spec": spec}


def pick(question):
    """Which view a question needs: why -> evidence; backtest/follow/return -> backtest; change/when -> stance; else track_record."""
    q = question.lower()
    if any(w in q for w in ("why", "because", "evidence", "based on", "reason", "근거", "이유", "왜")):
        return "evidence"
    if any(w in q for w in ("backtest", "follow", "strategy", "rule", "return", "백테스트", "따라", "수익")):
        return "backtest"
    if any(w in q for w in ("change", "changed", "when", "over time", "flip", "turn", "변화", "바뀌", "언제")):
        return "stance"
    return "track_record"
