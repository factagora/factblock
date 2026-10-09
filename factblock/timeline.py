"""Timelines: what happened to each statement, drawn on one time axis, as known on a given day.

    t = factblock.timeline("brain/", as_of="2025-01-01", query="interest rates")
    t                                   # in Jupyter: the chart
    t.claims, t.events                  # the rows behind it, each with its block id and source
    t.with_series("fed-funds.csv")      # the same statements over a numeric series (prices, rates, ...)
    t.save("rates.html")                # .html needs nothing; .png and .svg need vl-convert-python
    t.spec()                            # the Vega-Lite spec, for a web page or a chat answer

Two drawings, each one idea. Without a series, one bar per statement from the day it was said to the day it was
replaced, judged or due, coloured by what became of it, with the statement written next to it (group the rows
with group_by). With a series, a line with each statement as a labelled point on the day it was said. The full
history of each statement (took effect, learned late, replaced by what, every verdict) is in the tooltip and in
the rows. Everything is read as of `as_of`: a verdict, a replacement or a series value learned later is not drawn,
so the chart is the one you could have drawn that day.

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

RIGHT = {"true", "came_true", "kept", "mostly_true", "hit"}   # hit and miss: tckg's verdict vocabulary
WRONG = {"false", "did_not", "broken", "mostly_false", "misleading", "miss"}
STATUS = {"right": "#0ca30c", "wrong": "#d03b3b", "mixed": "#fab219", "open": "#8c8b85", "replaced": "#b8b7af"}
REASONS = {"CAUSES", "CONTRIBUTING_FACTOR", "TRIGGERS", "PREVENTS", "SUPPORTS"}
CONFIG = {"background": "#fcfcfb", "font": "Inter, system-ui, sans-serif",
          "axis": {"labelColor": "#52514e", "titleColor": "#52514e", "gridColor": "#ecebe7", "domainColor": "#c3c2b7", "tickColor": "#c3c2b7"},
          "legend": {"labelColor": "#52514e", "titleColor": "#52514e"},
          "title": {"color": "#0b0b0b", "subtitleColor": "#52514e", "anchor": "start", "fontSize": 15, "subtitleFontSize": 12},
          "view": {"stroke": None}}
SCHEMA = "factblock.timeline/v1"   # the shape of to_dict(); schemas/timeline.v1.schema.json
LIBS = ("vega@5.30.0", "vega-lite@5.21.0", "vega-embed@6.26.0")
DARK = {"background": "#1a1a19", "axis": {"labelColor": "#c3c2b7", "titleColor": "#c3c2b7", "gridColor": "#2e2e2b", "domainColor": "#52514e", "tickColor": "#52514e"},
        "legend": {"labelColor": "#c3c2b7", "titleColor": "#c3c2b7"}, "title": {"color": "#f0efec", "subtitleColor": "#c3c2b7"},
        "text": {"color": "#f0efec"}, "header": {"labelColor": "#f0efec"}}
# the page follows the reader's light or dark setting; text marks inherit the config colour in dark mode
HTML = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
{scripts}
<style>:root{{color-scheme:light dark}}body{{margin:16px;background:#fcfcfb;font-family:system-ui,sans-serif;overflow-x:auto}}
@media (prefers-color-scheme: dark){{body{{background:#1a1a19}}}}</style></head>
<body><div id="v"></div><script>
const spec = {spec};
if (matchMedia("(prefers-color-scheme: dark)").matches) {{
  const d = {dark};
  for (const k of Object.keys(d)) spec.config[k] = typeof d[k] === "object" ? Object.assign({{}}, spec.config[k], d[k]) : d[k];
  (function walk(o) {{ if (o && typeof o === "object") {{ if (o.color === "#0b0b0b") o.color = "#f0efec"; if (o.color === "#52514e") o.color = "#c3c2b7"; Object.values(o).forEach(walk); }} }})(spec);
}}
vegaEmbed("#v", spec, {{actions: false}});
</script></body></html>
"""


# MCP Apps (the MCP UI extension, io.modelcontextprotocol/ui, protocol 2026-01-26): a tool that returns a timeline
# points at this resource; the host (Claude, ChatGPT, ...) renders it inline in the chat and hands it the tool result.
MCP_APP_URI = "ui://factblock/timeline"
MCP_APP_MIME = "text/html;profile=mcp-app"
MCP_APP_META = {"ui": {"csp": {"resourceDomains": ["https://cdn.jsdelivr.net"]}, "prefersBorder": True}}
MCP_APP_TOOL_META = {"ui": {"resourceUri": MCP_APP_URI}}
VL_META = "factblock/vega-lite"   # where the spec travels in the tool result: _meta, so it stays out of the model's context
MCP_APP = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
{scripts}
<style>:root{{color-scheme:light dark}}body{{margin:0;padding:12px;background:transparent;font-family:system-ui,sans-serif;overflow-x:auto}}
#v{{min-height:40px}}#t{{white-space:pre-wrap;font-size:14px}}</style></head>
<body><div id="v"></div><div id="t"></div><script>
const DARK = {dark};
let seq = 0, theme = "light", last = null;
const waiting = {{}};
const post = m => window.parent.postMessage(Object.assign({{jsonrpc: "2.0"}}, m), "*");
const ask = (method, params) => new Promise(ok => {{ const id = ++seq; waiting[id] = ok; post({{id, method, params}}); }});
const size = () => post({{method: "ui/notifications/size-changed", params: {{width: document.body.scrollWidth, height: document.body.scrollHeight}}}});
function draw(result) {{
  last = result;
  const spec = JSON.parse(JSON.stringify((result._meta || {{}})["{vl_meta}"] || {{}}));
  if (!spec.mark && !spec.layer && !spec.facet && !spec.vconcat) {{
    document.getElementById("t").textContent = ((result.content || [])[0] || {{}}).text || ""; return size();
  }}
  if (theme === "dark") {{
    for (const k of Object.keys(DARK)) spec.config[k] = typeof DARK[k] === "object" ? Object.assign({{}}, spec.config[k], DARK[k]) : DARK[k];
    (function walk(o) {{ if (o && typeof o === "object") {{ if (o.color === "#0b0b0b") o.color = "#f0efec"; if (o.color === "#52514e") o.color = "#c3c2b7"; Object.values(o).forEach(walk); }} }})(spec);
  }}
  (function strip(o) {{ if (o && typeof o === "object") {{ delete o.href; Object.values(o).forEach(strip); }} }})(spec);   // links go through the host
  const w = Math.max(320, document.body.clientWidth - (spec.facet ? 110 : 30));   // fit the chat column; the legend sits below
  if (spec.facet) spec.spec.width = w; else spec.width = w;
  vegaEmbed("#v", spec, {{actions: false}}).then(r => {{
    r.view.addEventListener("click", (e, item) => {{ const u = item && item.datum && item.datum.source; if (u) ask("ui/open-link", {{url: u}}); }});
    size();
  }});
}}
window.addEventListener("message", e => {{
  const m = e.data;
  if (!m || m.jsonrpc !== "2.0") return;
  if (m.id !== undefined && waiting[m.id]) {{ waiting[m.id](m.result); delete waiting[m.id]; return; }}
  if (m.method === "ui/notifications/tool-result") draw(m.params);
  else if (m.method === "ui/notifications/host-context-changed" && m.params && m.params.theme) {{ theme = m.params.theme; if (last) draw(last); }}
  else if (m.method === "ui/resource-teardown") post({{id: m.id, result: {{}}}});
}});
ask("ui/initialize", {{protocolVersion: "2026-01-26", appInfo: {{name: "factblock-timeline", version: "1"}}, appCapabilities: {{}}}}).then(r => {{
  theme = (r && r.hostContext && r.hostContext.theme) || theme;
  post({{method: "ui/notifications/initialized", params: {{}}}});
}});
</script></body></html>
"""


def mcp_app_html(inline: bool = False) -> str:
    """The MCP Apps view for timelines: serve it as the resource MCP_APP_URI with MCP_APP_MIME and MCP_APP_META, and
    give the tool _meta=MCP_APP_TOOL_META. It renders whatever Timeline.to_mcp() returns, follows the host's theme,
    reports its height and opens sources through the host. inline=True needs no CDN (then drop the csp meta)."""
    return MCP_APP.format(scripts=_scripts(inline), dark=json.dumps(DARK), vl_meta=VL_META)


def _scripts(inline):
    """Script tags for vega, vega-lite and vega-embed: from the CDN, or the code itself (for sandboxes that block
    the network, such as MCP Apps iframes). Inline copies are fetched once and kept in ~/.cache/factblock."""
    if not inline:
        return "\n".join(f'<script src="https://cdn.jsdelivr.net/npm/{lib}"></script>' for lib in LIBS)
    import urllib.request
    cache = Path.home() / ".cache" / "factblock"
    cache.mkdir(parents=True, exist_ok=True)
    out = []
    for lib in LIBS:
        f = cache / f"{lib}.js"
        if not f.exists():
            urllib.request.urlretrieve(f"https://cdn.jsdelivr.net/npm/{lib}", f)
        out.append("<script>" + f.read_text().replace("</script", "<\\/script") + "</script>")
    return "\n".join(out)


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
        return {"schema": SCHEMA, "as_of": self.as_of, "title": self.title, "claims": self.claims, "events": self.events,
                "series": [{"t": _day(d), "value": v} for d, v in self.series] if self.series else None,
                "series_name": self.series_name, "certificate": self.certificate}

    def spec(self, width: int = 760) -> dict:
        """The Vega-Lite v5 spec: one bar per statement, or with a series, the line with each statement as a labelled point."""
        body = _series_spec(self, width) if self.series else _bars_spec(self, width)
        return {"$schema": "https://vega.github.io/schema/vega-lite/v5.json", "config": CONFIG, **body}

    def to_html(self, inline: bool = False) -> str:
        """The chart as one HTML page that follows the reader's light or dark setting. inline=True puts the
        Vega code in the page (about 800 KB) so it renders with no network, as in an MCP Apps iframe."""
        return HTML.format(title=self.title, scripts=_scripts(inline), spec=json.dumps(self.spec(), default=str), dark=json.dumps(DARK))

    def to_markdown(self) -> str:
        """The chart as text, for a chat answer or any place that cannot draw: one line per statement with what
        became of it and a link to its source."""
        lines = [f"**{self.title}**", ""]
        for c in self.claims:
            what = {"right": "right", "wrong": "wrong", "mixed": "mixed", "open": "open", "replaced": "replaced"}[c["status"]]
            tail = f" (verdict {c['verdict']})" if c["verdict"] else (f", due {c['due']}" if c["due"] else "")
            src = f" [source]({c['source']})" if c["source"] else ""
            lines.append(f"- {c['said']} · {c['statement']} **{what}**{tail}{src} `{c['id']}`")
        lines += ["", f"_As known on {self.as_of[:10]}: nothing learned later is shown._"]
        return "\n".join(lines)

    def to_mcp(self) -> dict:
        """A tool result for any MCP server: the markdown for the model and for hosts that cannot draw, the rows as
        structuredContent, and the Vega-Lite spec in _meta for the MCP Apps view (mcp_app_html). Return it as a
        CallToolResult(content=..., structuredContent=..., _meta=...)."""
        return {"content": [{"type": "text", "text": self.to_markdown()}],
                "structuredContent": json.loads(json.dumps(self.to_dict(), default=str)),
                "_meta": {VL_META: json.loads(json.dumps(self.spec(), default=str))}}

    def save(self, path, inline: bool = False) -> Path:
        """Write the chart: .html (opens in a browser; inline=True for no network), .md (text), .json (the data,
        schema factblock.timeline/v1), .vl.json (the spec), .png or .svg (need `pip install vl-convert-python`)."""
        path = Path(path)
        name = path.name.lower()
        if name.endswith(".vl.json"):
            path.write_text(json.dumps(self.spec(), indent=1, default=str))
        elif name.endswith(".json"):
            path.write_text(json.dumps(self.to_dict(), indent=1, default=str))
        elif name.endswith(".html"):
            path.write_text(self.to_html(inline))
        elif name.endswith(".md"):
            path.write_text(self.to_markdown() + "\n")
        elif name.endswith((".png", ".svg")):
            try:
                import vl_convert as vlc
            except ImportError:
                raise ImportError("PNG and SVG need vl-convert: pip install vl-convert-python (or save as .html)") from None
            spec = json.loads(json.dumps(self.spec(), default=str))
            data = vlc.vegalite_to_png(spec, scale=2) if name.endswith(".png") else vlc.vegalite_to_svg(spec).encode()
            path.write_bytes(data)
        else:
            raise ValueError(f"unknown format for {path}: use .html, .md, .png, .svg, .json or .vl.json")
        return path

    def _repr_mimebundle_(self, include=None, exclude=None):
        return {"application/vnd.vegalite.v5+json": json.loads(json.dumps(self.spec(), default=str)), "text/plain": repr(self)}

    def __repr__(self):
        return f"<Timeline as of {self.as_of[:10]}: {len(self.claims)} statements, {len(self.events)} events{', with ' + self.series_name if self.series else ''}>"


def timeline(bundle: BundleLike, as_of: Instant, query: str = "", *, ids: list[str] | None = None,
             kinds: tuple[str, ...] | None = None, limit: int = 30, valid_at: Instant | None = None,
             series=None, series_name: str | None = None, group_by: str | None = None) -> Timeline:
    """Use to see what happened to statements over time, as known on as_of: one bar per statement from when it was
    said to when it was replaced, judged or due, coloured by the outcome. Pick statements by `query` (recall's
    keyword match; "" for all, newest first), by `ids`, and `kinds`; at most `limit`. `group_by` names a payload
    field (speaker, customer, asset) to group the rows by. Pass `series` (a CSV path or (date, value) pairs) to
    draw them as points on a numeric series, as with_series() does."""
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
        mine = [x for x in events if x["id"] == n["id"]]
        stops = [x["t"] for x in mine if x["event"] == "replaced"] + [_day(r["decided_at"]) for r in verdicts if r["target_id"] == n["id"]] + ([_day(due)] if due else [])
        claims.append({"id": n["id"], "lane": lane_of[n["id"]], "kind": n["kind"], "statement": n.get("statement"),
                       "label": _short(n.get("statement"), 70), "said": _day(n["asserted_at"]), "end": min(stops) if stops else _day(t),
                       "due": _day(due) if due else None, "direction": p.get("direction"), "speaker": p.get("speaker"),
                       "group": str(p.get(group_by, n.get(group_by)) or "other") if group_by else None,
                       "source": _url(p), "reasons": reasons, "status": status, "verdict": (v.get("outcome") or v.get("value")) if v else None})
    for r in verdicts:
        n = by[r["target_id"]]
        o = r.get("outcome") or r.get("value")
        ev(n, r["decided_at"], f"verdict: {_outcome(o)}", f"{o} (decided {_day(r['decided_at'])}" + (f" by {r['resolver']})" if r.get("resolver") else ")"))
    events.sort(key=lambda e: (e["t"], e["lane"]))
    for c in claims:   # the whole story of a statement in one line, for the tooltip
        c["history"] = "; ".join(f"{e['t']} {e['event']}" + (f" ({e['detail']})" if e["detail"] and e["event"] != "said" else "") for e in events if e["id"] == c["id"])
    what = f"about {query!r}" if query else ("selected" if ids else "the newest")
    title = f"{len(claims)} statements, {what}, as known on {_day(t)}" if what != "the newest" else f"The {len(claims)} newest statements, as known on {_day(t)}"
    tl = Timeline(t.isoformat(), claims, events, cert, title)
    return tl.with_series(series, series_name) if series is not None else tl


def _when(day):
    d = parse_instant(day)
    return {"year": d.year, "month": d.month, "date": d.day}


LEGEND_BELOW = {**CONFIG, "legend": {**CONFIG["legend"], "orient": "bottom", "direction": "horizontal"}}   # the chart keeps the width of a narrow chat column


def _as_of_rule(tl):
    return {"mark": {"type": "rule", "strokeDash": [4, 4], "color": "#52514e"}, "encoding": {"x": {"datum": _when(tl.as_of[:10]), "type": "temporal"}}}


def _status(title="What became of it"):
    return {"field": "status", "type": "nominal", "title": title, "scale": {"domain": list(STATUS), "range": list(STATUS.values())}}


TIP = [{"field": "statement"}, {"field": "status", "title": "as known"}, {"field": "history"}, {"field": "id", "title": "FactBlock id"}, {"field": "source"}]


def _bars_spec(tl, width):
    lo, hi = parse_instant(min(c["said"] for c in tl.claims)), parse_instant(tl.as_of)
    span = max((hi - lo).days, 1)
    rows = []
    for c in tl.claims:   # a bar at least visible; its label goes on the side with more room, and stops at the edge
        end = max(c["end"], _day(parse_instant(c["said"]) + timedelta(days=max(2, span // 150))))
        rows.append({**c, "end": end, "right": (parse_instant(end) - lo) > (hi - parse_instant(c["said"]))})
    y = {"field": "lane", "type": "nominal", "sort": [c["lane"] for c in tl.claims], "axis": None}
    x = {"field": "said", "type": "temporal", "title": None, "axis": {"format": "%b %Y", "tickCount": 8, "orient": "top"}}
    text = {"type": "text", "baseline": "bottom", "dy": -7, "fontSize": 11.5, "color": "#0b0b0b"}   # longer text ends in an ellipsis
    layer = [
        _as_of_rule(tl),
        {"mark": {"type": "bar", "height": 9, "cornerRadius": 4.5, "cursor": "pointer"},
         "encoding": {"x": x, "x2": {"field": "end"}, "y": y, "color": _status(), "href": {"field": "source"}, "tooltip": TIP}},
        {"transform": [{"filter": "!datum.right"}], "mark": {**text, "align": "left", "limit": {"expr": "range('x')[1] - scale('x', datum.said) - 4"}}, "encoding": {"x": {"field": "said", "type": "temporal"}, "y": y, "text": {"field": "label"}}},
        {"transform": [{"filter": "datum.right"}], "mark": {**text, "align": "right", "limit": {"expr": "scale('x', datum.end)"}}, "encoding": {"x": {"field": "end", "type": "temporal"}, "y": y, "text": {"field": "label"}}},
    ]
    title = {"text": tl.title, "subtitle": ["Each bar runs from the day a statement was said",   # short lines: titles do not wrap
                                            "to the day it was replaced, judged or due, coloured by",
                                            f"what became of it as known on {tl.as_of[:10]}. Hover for its history."]}
    if any(c["group"] for c in tl.claims):
        return {"title": title, "data": {"values": rows}, "facet": {"row": {"field": "group", "title": None, "header": {"labelAngle": 0, "labelAlign": "left", "labelFontSize": 13, "labelFontWeight": 600}}},
                "spec": {"width": width, "height": {"step": 34}, "layer": layer}, "resolve": {"scale": {"y": "independent"}}, "config": LEGEND_BELOW}
    return {"title": title, "data": {"values": rows}, "width": width, "height": {"step": 34}, "layer": layer, "config": LEGEND_BELOW}


def _series_spec(tl, width):
    days = [d for d, _ in tl.series]

    def at(day):
        i = bisect.bisect_right(days, parse_instant(day)) - 1
        return tl.series[i][1] if i >= 0 else None

    pts = [{**c, "v": at(c["said"]), "call": c["direction"] or "statement", "label": None} for c in tl.claims if at(c["said"]) is not None]
    # write out only a few: the settled ones, newest first, up to six; the rest are points with a tooltip
    settled = sorted((p for p in pts if p["status"] in ("right", "wrong", "mixed")), key=lambda p: p["said"], reverse=True)[:6]
    # labels close enough in time to collide split by value: the higher point's label above, the lower one's below
    span = max((parse_instant(tl.as_of) - days[0]).days, 1) if days else 1
    gap = lambda p, q: abs((parse_instant(p["said"]) - parse_instant(q["said"])).days)
    for i, p in enumerate(sorted(settled, key=lambda p: p["said"])):
        near = [q for q in settled if q is not p and gap(p, q) < 0.6 * span]
        p["label"], p["above"] = _short(p["statement"], 46), all(p["v"] >= q["v"] for q in near) if near else i % 2 == 0
        at_x = (parse_instant(p["said"]) - days[0]).days / span   # near an edge, the label runs inward
        p["align"] = "left" if at_x < 0.25 else "right" if at_x > 0.75 else "center"
    x = {"field": "t", "type": "temporal", "title": None, "axis": {"format": "%b %Y", "tickCount": 8}}
    px = {**x, "field": "said"}
    y = {"field": "v", "type": "quantitative", "title": tl.series_name, "scale": {"zero": False}}
    label = {"type": "text", "fontSize": 11, "color": "#0b0b0b", "align": {"expr": "datum.align"}, "limit": {"expr": "width * 0.3"}}   # labels further apart than 0.6 of the span never touch
    return {
        "title": {"text": tl.title, "subtitle": [f"{tl.series_name}, with each statement where it was said,",
                                                 f"coloured by what became of it as known on {tl.as_of[:10]}.",
                                                 "Settled ones are labelled; hover any point for its history."]},
        "config": LEGEND_BELOW,
        "width": width, "height": 320,
        "layer": [
            {"data": {"values": [{"t": _day(d), "v": v} for d, v in tl.series]}, "mark": {"type": "line", "color": "#52514e", "strokeWidth": 1.5},
             "encoding": {"x": x, "y": y, "tooltip": [{"field": "t", "type": "temporal", "format": "%d %b %Y"}, {"field": "v", "title": tl.series_name}]}},
            _as_of_rule(tl),
            {"data": {"values": pts}, "mark": {"type": "point", "filled": True, "size": 110, "stroke": "#fcfcfb", "strokeWidth": 1.5, "opacity": 1, "cursor": "pointer"},
             "encoding": {"x": px, "y": y, "color": _status(), "href": {"field": "source"}, "tooltip": TIP,
                          "shape": {"field": "call", "type": "nominal", "title": "Call", "scale": {"domain": ["up", "down", "statement"], "range": ["triangle-up", "triangle-down", "circle"]}}}},
            {"data": {"values": pts}, "transform": [{"filter": "datum.label && datum.above"}], "mark": {**label, "dy": -12, "baseline": "bottom"}, "encoding": {"x": px, "y": y, "text": {"field": "label"}}},
            {"data": {"values": pts}, "transform": [{"filter": "datum.label && !datum.above"}], "mark": {**label, "dy": 12, "baseline": "top"}, "encoding": {"x": px, "y": y, "text": {"field": "label"}}},
        ],
    }
