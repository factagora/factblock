"""Recall: the blocks about something, as of an instant. The read an agent makes before it answers.
Keyword matching over statement, quote and speaker (a term hits a word when they are equal, or share a
stem of four or more characters), ranked by how many query terms hit, then by recency of assertion. Same visibility rule as scan, same certificate, so what a recall hides is said.
ponytail: substring and prefix matching, no embeddings; add a vector rank when declarations.embedding
is set and a bundle with vectors shows up."""
import re

from .bundle import Bundle
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
    nodes, _, _, cert = visible(b, as_of, valid_at)
    terms = _terms(query)
    items = []
    for n in nodes:
        if kinds and n["kind"] not in kinds:
            continue
        payload = n.get("payload") or {}
        score = _hits(terms, n)
        if score:
            items.append({"id": n["id"], "kind": n["kind"], "statement": n.get("statement"), "asserted_at": n["asserted_at"],
                          "speaker": payload.get("speaker"), "score": score})
    items.sort(key=lambda x: (-x["score"], -x["asserted_at"].timestamp()))
    return {"query": query, "as_of": cert["as_of"], "items": items[:limit], "matched": len(items), "certificate": cert}


def context(bundle, query, as_of, valid_at=None, limit=10) -> str:
    """The recall as lines for a prompt: one dated statement per line, then what was hidden."""
    r = recall(bundle, query, as_of, valid_at, limit)
    lines = [f"- {i['asserted_at'].date().isoformat()}" + (f" {i['speaker']}:" if i.get("speaker") else ":") + f" {i['statement']}" for i in r["items"]]
    m = r["certificate"].get("masked", {})
    if m:
        lines.append(f"(as of {r['as_of'][:10]}; {sum(m.values())} later blocks hidden)")
    return "\n".join(lines)
