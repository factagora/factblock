"""Recall: the blocks about something, as of an instant. The read an agent makes before it answers.
Keyword matching over the statement and the payload's text fields (speaker, quote, imported columns): a term
hits a word when they are equal or share a stem of four or more characters ("cost" finds "costs", "price" does
not find "costs"). Ranked by how many query terms hit, then by recency of assertion; an empty query matches all. Same visibility rule as scan, same certificate, so what a recall hides is said.

Each item also carries what happened to the block afterwards, as far as it was known at as_of: the block
that replaced it (a SUPERSEDES row), its latest verdict (a resolutions row), where it came from
(payload.source) and when it was learned (known_at). These are separate rows with their own known_at,
so a correction or verdict learned later than as_of is not shown. This is the part a date filter cannot do.

One exception to the visibility rule: a block whose validity ended before valid_at (a prediction past its
horizon, a promise past its deadline) but that has a verdict known by as_of is kept and marked `ended`.
Its verdict is what "did it happen?" asks for; hiding the block the moment it was settled would hide the answer.
ponytail: substring and prefix matching, no embeddings; add a vector rank when declarations.embedding
is set and a bundle with vectors shows up."""
import re

from .bundle import Bundle, BundleLike, Instant, parse_instant
from .scan import visible

THINGS = ("entity", "factor", "timeseries", "episode")   # core kinds that are not statements someone made


def _terms(q):
    return [t for t in re.findall(r"\w+", q.lower()) if len(t) > 1]


def _words(n):
    """The node's words, computed once per node and kept on the row."""
    if "_words" not in n:
        payload = n.get("payload") or {}
        # the statement plus every short text field of the payload: speaker, quote, and the columns an import put there
        text = " ".join([n.get("statement") or ""] + [v for v in payload.values() if isinstance(v, str) and len(v) < 2000])
        n["_words"] = set(re.findall(r"\w+", text.lower()))
        n["_pre4"] = {w[:4] for w in n["_words"]}          # prefix matches are only tried where a 4-char stem agrees
    return n["_words"]


def _hits(terms, n):
    words, pre4 = _words(n), n["_pre4"]
    return sum(1 for t in terms if t in words or (len(t) > 3 and t[:4] in pre4 and any(w.startswith(t) or t.startswith(w) for w in words)))


def recall(bundle: BundleLike, query: str, as_of: Instant, valid_at: Instant | None = None, limit: int = 10,
           kinds: tuple[str, ...] | None = None, verdict: str | None = None) -> dict:
    """Use before an agent answers: the blocks matching `query` as known at `as_of`, ranked, each with what
    replaced it, its verdict, source and known_at. Returns {"items", "matched", "excluded", "certificate", ...}.
    `kinds` None means every kind of statement (claims, predictions, commitments, any kind you use) but not
    the things they are about (entity, factor, timeseries, episode); () means every kind; a tuple means
    exactly those. Matches dropped by `kinds` are counted per kind in `excluded`. An empty query matches every
    block, newest first. `verdict` keeps only blocks whose latest visible verdict is that outcome (e.g. "did_not"),
    or "open" (none yet) or "resolved" (any)."""
    b = bundle if isinstance(bundle, Bundle) else Bundle(bundle)
    nodes, _, res, cert = visible(b, as_of, valid_at)
    terms = _terms(query)
    by_id = {n["id"]: n for n in nodes}
    raw = None
    verdicts = {}
    for r in res:   # latest decided verdict known by as_of
        if r["target_id"] not in verdicts or r["decided_at"] > verdicts[r["target_id"]]["decided_at"]:
            verdicts[r["target_id"]] = r
    t, va = parse_instant(cert["as_of"]), parse_instant(cert["valid_at"])
    ended = [n for n in b.nodes if n["id"] in verdicts and n["id"] not in by_id and n["known_at"] <= t
             and n.get("valid_to") is not None and n["valid_to"] <= va and n["asserted_at"] <= va]
    wanted = lambda n: n["kind"] not in THINGS if kinds is None else not kinds or n["kind"] in kinds   # noqa: E731
    nodes = nodes + [{**n, "superseded_by": None, "_ended": True} for n in ended]
    items, excluded = [], {}
    for n in nodes:
        payload = n.get("payload") or {}
        score = _hits(terms, n) if terms else 1
        v = verdicts.get(n["id"])
        if verdict and not (v is None if verdict == "open" else v is not None and verdict in ("resolved", v.get("outcome") or v.get("value"))):
            continue
        if score and not wanted(n):
            excluded[n["kind"]] = excluded.get(n["kind"], 0) + 1
            continue
        if score:
            item = {"id": n["id"], "kind": n["kind"], "statement": n.get("statement"), "asserted_at": n["asserted_at"],
                    "known_at": n["known_at"], "speaker": payload.get("speaker"), "source": payload.get("source"), "score": score}
            if n.get("_ended"):
                item["ended"] = n["valid_to"]
            if n.get("superseded_by"):
                succ = by_id.get(n["superseded_by"])
                if succ is None:   # the replacing edge is visible; its block may not be in force at valid_at
                    raw = raw or {x["id"]: x for x in b.nodes}
                    succ = raw.get(n["superseded_by"], {"id": n["superseded_by"]})
                item["superseded_by"] = {"id": succ["id"], "statement": succ.get("statement"), "asserted_at": succ.get("asserted_at"),
                                         "since": n["_replaced_at"]}
            if v:
                item["verdict"] = {"outcome": v.get("outcome") or v.get("value"), "decided_at": v["decided_at"], "resolver": v.get("resolver")}
            items.append(item)
    items.sort(key=lambda x: (-x["score"], -x["asserted_at"].timestamp()))
    matched, items = len(items), items[:limit]

    # announced but not in force yet: known by as_of and said by valid_at, taking effect later. A change to a shown
    # block goes on that block ("upcoming"); other matching announcements are listed on their own.
    soon = lambda r: r["known_at"] <= t and r["asserted_at"] <= va and r["valid_from"] > va   # noqa: E731
    pending = {n["id"]: n for n in b.nodes if soon(n)}
    shown, attached, upcoming = {i["id"]: i for i in items}, set(), []
    if not verdict:
        for e in b.edges:
            if e["edge_type"] == "SUPERSEDES" and soon(e) and e["target_id"] in shown and e["source_id"] in pending:
                s = pending[e["source_id"]]
                shown[e["target_id"]]["upcoming"] = {"id": s["id"], "statement": s.get("statement"), "asserted_at": s["asserted_at"], "from": e["valid_from"]}
                attached.add(s["id"])
        upcoming = sorted(({"id": n["id"], "kind": n["kind"], "statement": n.get("statement"), "asserted_at": n["asserted_at"], "from": n["valid_from"]}
                           for n in pending.values() if n["id"] not in attached and wanted(n) and (_hits(terms, n) if terms else 1)),
                          key=lambda x: x["from"])
    return {"query": query, "as_of": cert["as_of"], "items": items, "matched": matched, "upcoming": upcoming,
            "excluded": excluded, "certificate": cert}


def _source(s):
    if isinstance(s, dict):
        return s.get("title") or s.get("url")
    return s


def context(bundle: BundleLike, query: str, as_of: Instant, valid_at: Instant | None = None, limit: int = 10,
            kinds: tuple[str, ...] | None = None, verdict: str | None = None) -> str:
    """Use to put memory into a prompt. The recall as lines: one dated statement per line, indented lines for what happened
    to it since (replaced, about to change, verdict), announced changes not in force yet, then what was hidden. Learned-later and source go on the first line. Never empty:
    when nothing matches it says so, so the model is told it has no memory of this rather than nothing at all."""
    r = recall(bundle, query, as_of, valid_at, limit, kinds, verdict)
    lines = [] if r["items"] or r["upcoming"] else [f"(nothing about {query!r} known as of {r['as_of'][:10]})"]
    for i in r["items"]:
        head = f"- {i['asserted_at'].date().isoformat()}" + (f" {i['speaker']}:" if i.get("speaker") else ":") + f" {i['statement']}"
        notes = []
        if (i["known_at"] - i["asserted_at"]).days >= 1:
            notes.append(f"learned {i['known_at'].date().isoformat()}")
        if _source(i.get("source")):
            notes.append(f"source: {_source(i['source'])}")
        lines.append(head + (f" ({'; '.join(notes)})" if notes else ""))
        if i.get("ended"):
            lines.append(f"  ended {i['ended'].date().isoformat()}")
        if i.get("superseded_by"):
            s = i["superseded_by"]
            said = s["asserted_at"].date().isoformat() if s.get("asserted_at") else None
            when = s["since"].date().isoformat()
            lines.append(f"  replaced {when} by: {s.get('statement') or s['id']}" + (f" (announced {said})" if said and said != when else ""))
        if i.get("upcoming"):
            u = i["upcoming"]
            lines.append(f"  changes {u['from'].date().isoformat()} to: {u['statement'] or u['id']} (announced {u['asserted_at'].date().isoformat()})")
        if i.get("verdict"):
            v = i["verdict"]
            lines.append(f"  verdict: {v['outcome']} (decided {v['decided_at'].date().isoformat()}" + (f" by {v['resolver']})" if v.get("resolver") else ")"))
    for u in r["upcoming"]:
        lines.append(f"- {u['asserted_at'].date().isoformat()}: {u['statement'] or u['id']} (takes effect {u['from'].date().isoformat()})")
    m = r["certificate"].get("masked", {})
    if m:
        n = sum(m.values())
        lines.append(f"(as of {r['as_of'][:10]}; {n} later block{'s' if n != 1 else ''} hidden)")
    return "\n".join(lines)
