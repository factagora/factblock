"""Recall: the blocks about something, as of an instant. The read an agent makes before it answers.
Keyword matching over statement, quote and speaker (a term hits a word when they are equal, or share a
stem of four or more characters), ranked by how many query terms hit, then by recency of assertion. Same visibility rule as scan, same certificate, so what a recall hides is said.

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

from .bundle import Bundle, parse_instant
from .scan import visible

DEFAULT_KINDS = ("claim", "prediction")


def _terms(q):
    return [t for t in re.findall(r"\w+", q.lower()) if len(t) > 1]


def _words(n):
    """The node's words, computed once per node and kept on the row."""
    if "_words" not in n:
        payload = n.get("payload") or {}
        text = " ".join(str(x) for x in (n.get("statement"), payload.get("quote"), payload.get("speaker")) if x)
        n["_words"] = set(re.findall(r"\w+", text.lower()))
        n["_pre4"] = {w[:4] for w in n["_words"]}          # prefix matches are only tried where a 4-char stem agrees
    return n["_words"]


def _hits(terms, n):
    words, pre4 = _words(n), n["_pre4"]
    return sum(1 for t in terms if t in words or (len(t) > 3 and t[:4] in pre4 and any(w.startswith(t) or t.startswith(w) for w in words)))


def recall(bundle, query, as_of, valid_at=None, limit=10, kinds=DEFAULT_KINDS) -> dict:
    b = bundle if isinstance(bundle, Bundle) else Bundle(bundle)
    nodes, _, res, cert = visible(b, as_of, valid_at)
    terms = _terms(query)
    by_id = {n["id"]: n for n in nodes}
    raw = None
    verdicts = {}
    for r in res:   # latest decided verdict known by as_of
        if r["target_id"] not in verdicts or r["decided_at"] > verdicts[r["target_id"]]["decided_at"]:
            verdicts[r["target_id"]] = r
    t, v = parse_instant(cert["as_of"]), parse_instant(cert["valid_at"])
    ended = [n for n in b.nodes if n["id"] in verdicts and n["id"] not in by_id and n["known_at"] <= t
             and n.get("valid_to") is not None and n["valid_to"] <= v and n["asserted_at"] <= v]
    nodes = nodes + [{**n, "superseded_by": None, "_ended": True} for n in ended]
    items = []
    for n in nodes:
        if kinds and n["kind"] not in kinds:
            continue
        payload = n.get("payload") or {}
        score = _hits(terms, n)
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
                item["superseded_by"] = {"id": succ["id"], "statement": succ.get("statement"), "asserted_at": succ.get("asserted_at")}
            v = verdicts.get(n["id"])
            if v:
                item["verdict"] = {"outcome": v.get("outcome") or v.get("value"), "decided_at": v["decided_at"], "resolver": v.get("resolver")}
            items.append(item)
    items.sort(key=lambda x: (-x["score"], -x["asserted_at"].timestamp()))
    return {"query": query, "as_of": cert["as_of"], "items": items[:limit], "matched": len(items), "certificate": cert}


def _source(s):
    if isinstance(s, dict):
        return s.get("title") or s.get("url")
    return s


def context(bundle, query, as_of, valid_at=None, limit=10) -> str:
    """The recall as lines for a prompt: one dated statement per line, indented lines for what happened
    to it since (replaced, verdict), then what was hidden. Learned-later and source go on the first line."""
    r = recall(bundle, query, as_of, valid_at, limit)
    lines = []
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
            when = s["asserted_at"].date().isoformat() if s.get("asserted_at") else "later"
            lines.append(f"  replaced {when} by: {s.get('statement') or s['id']}")
        if i.get("verdict"):
            v = i["verdict"]
            lines.append(f"  verdict: {v['outcome']} (decided {v['decided_at'].date().isoformat()}" + (f" by {v['resolver']})" if v.get("resolver") else ")"))
    m = r["certificate"].get("masked", {})
    if m:
        n = sum(m.values())
        lines.append(f"(as of {r['as_of'][:10]}; {n} later block{'s' if n != 1 else ''} hidden)")
    return "\n".join(lines)
