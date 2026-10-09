"""Timelines: what happened to each statement, drawn on one time axis, as known on a given day.

    t = factblock.timeline("brain/", as_of="2025-01-01", query="interest rates")
    t                                   # in Jupyter: the chart
    t.claims, t.events                  # the rows behind it, each with its block id and source
    t.with_series("fed-funds.csv")      # the same statements over a numeric series (prices, rates, ...)
    t.save("rates.html")                # .html needs nothing; .png and .svg need vl-convert-python
    t.spec()                            # the Vega-Lite spec, for a web page or a chat answer

One lane per statement. On it: when it was said, when it took effect if later, when it was learned if later,
the window until its horizon or deadline, when a later statement replaced it, and each verdict with its date.
Everything is read as of `as_of`: a verdict, a replacement or a series value learned later is not drawn, so the
chart is the one you could have drawn that day. With a series, each statement is also an arrow on the series
from the day it was said to its horizon (or as far as the series goes), coloured by its verdict.

The rows are plain dicts, so any renderer can draw them; spec() is the reference drawing."""
from __future__ import annotations

import bisect
import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

from .bundle import Bundle, BundleLike, Instant, parse_instant
from .recall import recall
from .scan import _as_of

RIGHT = {"true", "came_true", "kept", "mostly_true"}
WRONG = {"false", "did_not", "broken", "mostly_false", "misleading"}
STATUS = {"right": "#0ca30c", "wrong": "#d03b3b", "mixed": "#fab219", "open": "#8c8b85", "replaced": "#b8b7af"}
EVENTS = {"said": ("#2a78d6", "circle"), "in force": ("#2a78d6", "triangle-right"), "learned later": ("#6250d6", "diamond"),
          "replaced": ("#8c8b85", "square"), "verdict: right": ("#0ca30c", "triangle-up"), "verdict: wrong": ("#d03b3b", "cross"),
          "verdict: mixed": ("#fab219", "diamond")}
REASONS = {"CAUSES", "CONTRIBUTING_FACTOR", "TRIGGERS", "PREVENTS", "SUPPORTS"}
CONFIG = {"background": "#fcfcfb", "font": "Inter, system-ui, sans-serif",
          "axis": {"labelColor": "#52514e", "titleColor": "#52514e", "gridColor": "#ecebe7", "domainColor": "#c3c2b7", "tickColor": "#c3c2b7"},
          "legend": {"labelColor": "#52514e", "titleColor": "#52514e"},
          "title": {"color": "#0b0b0b", "subtitleColor": "#52514e", "anchor": "start", "fontSize": 15, "subtitleFontSize": 12},
          "view": {"stroke": None}}
HTML = """<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>
<script src="https://cdn.jsdelivr.net/npm/vega@5.30.0"></script>
<script src="https://cdn.jsdelivr.net/npm/vega-lite@5.21.0"></script>
<script src="https://cdn.jsdelivr.net/npm/vega-embed@6.26.0"></script>
<style>body{{margin:24px;background:#fcfcfb;font-family:system-ui,sans-serif}}</style></head>
<body><div id="v"></div><script>vegaEmbed("#v", {spec}, {{actions: false}});</script></body></html>
"""


def _outcome(o):
    o = str(o or "")
    return "right" if o in RIGHT else "wrong" if o in WRONG else "mixed"


def _day(d):
    return d.date().isoformat() if isinstance(d, datetime) else str(d)[:10]


def _short(s, n=64):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _url(payload):
    src = (payload or {}).get("source")
    return src.get("url") if isinstance(src, dict) else (src if isinstance(src, str) and src.startswith("http") else None)


def read_series(series) -> list[tuple[datetime, float]]:
    """A numeric series as sorted (instant, value) pairs, from a CSV (first column a date, second a number;
    FRED downloads work as they are), or from (date, value) pairs or {"t", "value"} dicts. Blank or '.' values are skipped."""
    if isinstance(series, (str, Path)):
        with open(series, newline="") as f:
            rows = [r[:2] for r in csv.reader(f)][1:]
    else:
        rows = [(r["t"], r["value"]) if isinstance(r, dict) else r for r in series]
    out = []
    for t, v in rows:
        try:
            out.append((parse_instant(t), float(v)))
        except (TypeError, ValueError):
            continue
    return sorted(out)


class Timeline:
    """Statements and what happened to them, as known on as_of. Render with spec(), save(), or by leaving it as
    the last line of a Jupyter cell. claims and events are plain dicts for any other renderer."""

    def __init__(self, as_of, claims, events, certificate, title, series=None, series_name=None):
        self.as_of, self.claims, self.events, self.certificate, self.title = as_of, claims, events, certificate, title
        self.series, self.series_name = series, series_name

    def with_series(self, series, name: str | None = None) -> "Timeline":
        """The same timeline over a numeric series (a CSV path, (date, value) pairs or {"t", "value"} dicts).
        Values after as_of are dropped: the chart shows only what could be seen that day."""
        t = parse_instant(self.as_of)
        pts = [(d, v) for d, v in read_series(series) if d <= t]
        if not pts:
            raise ValueError("the series has no values on or before as_of; check the date column and as_of")
        name = name or (Path(series).stem if isinstance(series, (str, Path)) else "value")
        return Timeline(self.as_of, self.claims, self.events, self.certificate, self.title, pts, name)

    def to_dict(self) -> dict:
        """Everything behind the chart, JSON-ready: as_of, claims, events, series, certificate."""
        return {"as_of": self.as_of, "title": self.title, "claims": self.claims, "events": self.events,
                "series": [{"t": _day(d), "value": v} for d, v in self.series] if self.series else None,
                "series_name": self.series_name, "certificate": self.certificate}

    def spec(self, width: int = 760) -> dict:
        """The Vega-Lite v5 spec: lanes alone, or the series with each statement as an arrow above the lanes."""
        lanes = _lanes_spec(self, width)
        if not self.series:
            return {"$schema": "https://vega.github.io/schema/vega-lite/v5.json", "config": CONFIG,
                    "title": {"text": self.title, "subtitle": _subtitle(self)}, **lanes}
        return {"$schema": "https://vega.github.io/schema/vega-lite/v5.json", "config": CONFIG,
                "title": {"text": self.title, "subtitle": _subtitle(self)},
                "vconcat": [_series_spec(self, width), lanes], "resolve": {"scale": {"x": "shared", "color": "independent", "shape": "independent"}}}

    def save(self, path) -> Path:
        """Write the chart: .html (no dependencies, opens in a browser), .json (the data), .vl.json (the spec),
        .png or .svg (need `pip install vl-convert-python`)."""
        path = Path(path)
        name = path.name.lower()
        if name.endswith(".vl.json"):
            path.write_text(json.dumps(self.spec(), indent=1, default=str))
        elif name.endswith(".json"):
            path.write_text(json.dumps(self.to_dict(), indent=1, default=str))
        elif name.endswith(".html"):
            path.write_text(HTML.format(title=self.title, spec=json.dumps(self.spec(), default=str)))
        elif name.endswith((".png", ".svg")):
            try:
                import vl_convert as vlc
            except ImportError:
                raise ImportError("PNG and SVG need vl-convert: pip install vl-convert-python (or save as .html)") from None
            spec = json.loads(json.dumps(self.spec(), default=str))
            data = vlc.vegalite_to_png(spec, scale=2) if name.endswith(".png") else vlc.vegalite_to_svg(spec).encode()
            path.write_bytes(data)
        else:
            raise ValueError(f"unknown format for {path}: use .html, .png, .svg, .json or .vl.json")
        return path

    def _repr_mimebundle_(self, include=None, exclude=None):
        return {"application/vnd.vegalite.v5+json": json.loads(json.dumps(self.spec(), default=str)), "text/plain": repr(self)}

    def __repr__(self):
        return f"<Timeline as of {self.as_of[:10]}: {len(self.claims)} statements, {len(self.events)} events{', with ' + self.series_name if self.series else ''}>"


def timeline(bundle: BundleLike, as_of: Instant, query: str = "", *, ids: list[str] | None = None,
             kinds: tuple[str, ...] | None = None, limit: int = 30, valid_at: Instant | None = None,
             series=None, series_name: str | None = None) -> Timeline:
    """Use to see what happened to statements over time, as known on as_of: one lane per statement with when it
    was said, took effect, was learned, was replaced and was judged. Pick statements by `query` (recall's keyword
    match; "" for all, newest first), by `ids`, and `kinds`; at most `limit` lanes. Pass `series` (a CSV path or
    (date, value) pairs) to draw them over a numeric series, as with_series() does."""
    b = bundle if isinstance(bundle, Bundle) else Bundle(bundle)
    t = _as_of(as_of)
    if ids:
        want = set(ids)
        picked = [n for n in b.nodes if n["id"] in want and n["known_at"] <= t]
        missing = want - {n["id"] for n in picked}
        if missing:
            raise ValueError(f"not in the bundle as of {_day(t)}: {', '.join(sorted(missing))}")
        cert = recall(b, "", as_of, valid_at, limit=0)["certificate"]
    else:
        r = recall(b, query, as_of, valid_at, limit=limit, kinds=kinds)
        by = {n["id"]: n for n in b.nodes}
        picked, cert = [by[i["id"]] for i in r["items"]], r["certificate"]
    picked.sort(key=lambda n: (n["asserted_at"], n["id"]))
    lane_of, seen = {}, {}
    for n in picked:
        label = f"{_day(n['asserted_at'])}  {_short(n.get('statement'))}"
        seen[label] = seen.get(label, 0) + 1
        lane_of[n["id"]] = label if seen[label] == 1 else f"{label} ({seen[label]})"
    ids_ = set(lane_of)
    by = {n["id"]: n for n in b.nodes}
    verdicts = sorted((r for r in b.resolutions if r["target_id"] in ids_ and r["known_at"] <= t), key=lambda r: (r["decided_at"], r["known_at"]))
    edges = [e for e in b.edges if e["known_at"] <= t]

    events, claims = [], []

    def ev(n, at, kind, detail=None, other=None):
        events.append({"id": n["id"], "lane": lane_of[n["id"]], "t": _day(at), "event": kind, "statement": n.get("statement"),
                       "detail": detail, "other_id": other, "source": _url(n.get("payload"))})

    latest = {}
    for r in verdicts:
        latest[r["target_id"]] = r
    for n in picked:
        p = n.get("payload") or {}
        ev(n, n["asserted_at"], "said", p.get("speaker"))
        if _day(n["valid_from"]) != _day(n["asserted_at"]):
            ev(n, n["valid_from"], "in force", f"takes effect {_day(n['valid_from'])}")
        if n["known_at"] - n["asserted_at"] >= timedelta(days=1):
            ev(n, n["known_at"], "learned later", f"learned {_day(n['known_at'])}")
        reasons = 0
        for e in edges:
            if e["edge_type"] == "SUPERSEDES" and e["target_id"] == n["id"]:
                new = by.get(e["source_id"], {})
                ev(n, e["valid_from"], "replaced", f"replaced by: {_short(new.get('statement'), 120)}", e["source_id"])
            elif e["edge_type"] in REASONS and e["target_id"] == n["id"]:
                reasons += 1
        due = n.get("valid_to") if n["kind"] in ("prediction", "commitment") else None
        v = latest.get(n["id"])
        status = _outcome(v.get("outcome") or v.get("value")) if v else ("replaced" if any(x["id"] == n["id"] and x["event"] == "replaced" and x["t"] <= _day(t) for x in events) else "open")
        claims.append({"id": n["id"], "lane": lane_of[n["id"]], "kind": n["kind"], "statement": n.get("statement"),
                       "said": _day(n["asserted_at"]), "due": _day(due) if due else None, "direction": p.get("direction"),
                       "speaker": p.get("speaker"), "source": _url(p), "reasons": reasons, "status": status,
                       "verdict": (v.get("outcome") or v.get("value")) if v else None})
    for r in verdicts:
        n = by[r["target_id"]]
        o = r.get("outcome") or r.get("value")
        ev(n, r["decided_at"], f"verdict: {_outcome(o)}", f"{o} (decided {_day(r['decided_at'])}" + (f" by {r['resolver']})" if r.get("resolver") else ")"))
    events.sort(key=lambda e: (e["t"], e["lane"]))
    what = f"about {query!r}" if query else ("selected" if ids else "the newest")
    title = f"{len(claims)} statements, {what}, as known on {_day(t)}" if what != "the newest" else f"The {len(claims)} newest statements, as known on {_day(t)}"
    tl = Timeline(t.isoformat(), claims, events, cert, title)
    return tl.with_series(series, series_name) if series is not None else tl


def _subtitle(tl):
    s = ["One lane per statement: said, took effect, learned, replaced, judged. Nothing learned after the as-of day is drawn."]
    if tl.series:
        s.insert(0, f"Above: {tl.series_name}. Each statement sits on the day it was said; a call with a horizon is an arrow to it (or to the last value), coloured by its verdict.")
    return s


def _x(tl):
    return {"field": "t", "type": "temporal", "title": None, "axis": {"format": "%b %Y", "tickCount": 8}}


def _lanes_spec(tl, width):
    order = [c["lane"] for c in tl.claims]
    y = {"field": "lane", "type": "nominal", "title": None, "sort": order, "axis": {"labelLimit": 360, "labelFontSize": 11}}
    spans = [{"lane": c["lane"], "t": c["said"], "t2": c["due"], "id": c["id"]} for c in tl.claims if c["due"]]
    tip = [{"field": "t", "type": "temporal", "title": "date", "format": "%d %b %Y"}, {"field": "event"}, {"field": "statement"},
           {"field": "detail"}, {"field": "id", "title": "FactBlock id"}, {"field": "source"}]
    return {"width": width, "height": max(60, 22 * len(order)), "layer": [
        {"data": {"values": spans}, "mark": {"type": "rule", "strokeWidth": 7, "opacity": 0.22, "color": "#2a78d6", "strokeCap": "round"},
         "encoding": {"x": {"field": "t", "type": "temporal"}, "x2": {"field": "t2"}, "y": y,
                      "tooltip": [{"field": "t", "title": "said", "type": "temporal", "format": "%d %b %Y"}, {"field": "t2", "title": "horizon or deadline"}]}},
        {"data": {"values": [{"t": tl.as_of[:10]}]}, "mark": {"type": "rule", "strokeDash": [4, 4], "color": "#52514e"},
         "encoding": {"x": {"field": "t", "type": "temporal"}}},
        {"data": {"values": tl.events}, "mark": {"type": "point", "filled": True, "size": 90, "opacity": 1, "stroke": "#fcfcfb", "strokeWidth": 1.5, "cursor": "pointer"},
         "encoding": {"x": _x(tl), "y": y, "href": {"field": "source"},
                      "color": {"field": "event", "type": "nominal", "title": "Event", "scale": {"domain": list(EVENTS), "range": [c for c, _ in EVENTS.values()]}},
                      "shape": {"field": "event", "type": "nominal", "title": "Event", "scale": {"domain": list(EVENTS), "range": [s for _, s in EVENTS.values()]}},
                      "tooltip": tip}},
    ]}


def _series_spec(tl, width):
    days = [d for d, _ in tl.series]

    def at(day):
        i = bisect.bisect_right(days, parse_instant(day)) - 1
        return tl.series[i][1] if i >= 0 else None

    last = _day(tl.series[-1][0])
    arrows = []
    for c in tl.claims:
        y0 = at(c["said"])
        if y0 is None:
            continue
        end = min(c["due"], last) if c["due"] else c["said"]   # no horizon, no arrow: a mark where it was said
        arrows.append({**{k: c[k] for k in ("id", "statement", "status", "verdict", "source")}, "direction": c["direction"] or "statement",
                       "t": c["said"], "v": y0, "t2": end, "v2": at(end), "lane": c["lane"]})
    line = [{"t": _day(d), "v": v} for d, v in tl.series]
    x = _x(tl)
    color = {"field": "status", "type": "nominal", "title": "Verdict as known", "scale": {"domain": list(STATUS), "range": list(STATUS.values())}}
    tip = [{"field": "t", "type": "temporal", "title": "said", "format": "%d %b %Y"}, {"field": "statement"}, {"field": "direction"},
           {"field": "verdict"}, {"field": "id", "title": "FactBlock id"}, {"field": "source"}]
    return {"width": width, "height": 240, "layer": [
        {"data": {"values": line}, "mark": {"type": "line", "color": "#52514e", "strokeWidth": 1.5},
         "encoding": {"x": x, "y": {"field": "v", "type": "quantitative", "title": tl.series_name, "scale": {"zero": False}},
                      "tooltip": [{"field": "t", "type": "temporal", "format": "%d %b %Y"}, {"field": "v", "title": tl.series_name}]}},
        {"data": {"values": arrows}, "mark": {"type": "rule", "strokeWidth": 2, "opacity": 0.75},
         "encoding": {"x": x, "y": {"field": "v", "type": "quantitative"}, "x2": {"field": "t2"}, "y2": {"field": "v2"}, "color": color, "tooltip": tip}},
        {"data": {"values": arrows}, "mark": {"type": "point", "filled": True, "size": 80, "stroke": "#fcfcfb", "strokeWidth": 1.5, "cursor": "pointer"},
         "encoding": {"x": x, "y": {"field": "v", "type": "quantitative"}, "color": color, "href": {"field": "source"},
                      "shape": {"field": "direction", "type": "nominal", "title": "Call", "scale": {"domain": ["up", "down", "statement"], "range": ["triangle-up", "triangle-down", "circle"]}},
                      "tooltip": tip}},
    ]}
