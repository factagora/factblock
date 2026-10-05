"""Recall: the blocks about something, as of an instant. The read an agent makes before it answers.
Keyword matching over statement, quote and speaker, ranked by how many query terms hit, then by
recency of assertion. Same visibility rule as scan, same certificate, so what a recall hides is said.
ponytail: substring and prefix matching, no embeddings; add a vector rank when declarations.embedding
is set and a bundle with vectors shows up."""
import re

from .bundle import Bundle, parse_instant
from .scan import _as_of, _visible, scan

DEFAULT_KINDS = ("claim", "prediction")


def _terms(q):
    return [t for t in re.findall(r"\w+", q.lower()) if len(t) > 1]


def _hits(terms, text):
    words = re.findall(r"\w+", text.lower())
    return sum(1 for t in terms if any(w == t or (len(t) > 3 and (w.startswith(t) or t.startswith(w))) for w in words))


def recall(bundle, query, as_of, valid_at=None, limit=10, kinds=DEFAULT_KINDS) -> dict:
    b = bundle if isinstance(bundle, Bundle) else Bundle(bundle)
    s = scan(b, as_of, valid_at)
    t = _as_of(as_of); v = parse_instant(valid_at) if valid_at else t
    terms = _terms(query)
    items = []
    for n in b.nodes:
        if (kinds and n["kind"] not in kinds) or not _visible(n, t, v):
            continue
        payload = n.get("payload") or {}
        text = " ".join(str(x) for x in (n.get("statement"), payload.get("quote"), payload.get("speaker")) if x)
        score = _hits(terms, text)
        if score:
            items.append({"id": n["id"], "kind": n["kind"], "statement": n.get("statement"), "asserted_at": n["asserted_at"],
                          "speaker": payload.get("speaker"), "score": score})
    items.sort(key=lambda x: (-x["score"], -x["asserted_at"].timestamp()))
    return {"query": query, "as_of": s.certificate["as_of"], "items": items[:limit], "matched": len(items), "certificate": s.certificate}


def context(bundle, query, as_of, valid_at=None, limit=10) -> str:
    """The recall as lines for a prompt: one dated statement per line, then what was hidden."""
    r = recall(bundle, query, as_of, valid_at, limit)
    lines = [f"- {i['asserted_at'].date().isoformat()}" + (f" {i['speaker']}:" if i.get("speaker") else ":") + f" {i['statement']}" for i in r["items"]]
    m = r["certificate"].get("masked", {})
    if m:
        lines.append(f"(as of {r['as_of'][:10]}; {sum(m.values())} later blocks hidden)")
    return "\n".join(lines)
