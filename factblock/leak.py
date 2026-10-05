"""Hindsight check for an eval set. Each question says when it was asked and which blocks its
answer rests on; a block the system learned after that instant is a leak. Same visibility rule
as scan (SPEC 4.1), so a leak-free question set is one every answer could have been given then."""
import json
from pathlib import Path

from .bundle import Bundle, parse_instant
from .scan import _as_of, _visible


def _questions(q):
    if isinstance(q, (str, Path)):
        return [json.loads(l) for l in Path(q).read_text().splitlines() if l.strip()]
    return list(q)


def leak(bundle, questions) -> dict:
    """questions: a JSONL path or dicts of {id?, asked_at, evidence: [block id, ...]}."""
    b = bundle if isinstance(bundle, Bundle) else Bundle(bundle)
    rows = {r["id"]: r for r in b.nodes}
    out = []
    for i, q in enumerate(_questions(questions)):
        t = _as_of(q["asked_at"])
        v = parse_instant(q["valid_at"]) if q.get("valid_at") else t
        leaked, missing = [], []
        for nid in q.get("evidence", []):
            r = rows.get(nid)
            if r is None:
                missing.append(nid)
            elif not _visible(r, t, v):
                leaked.append({"id": nid, "known_at": r["known_at"].isoformat(), "asserted_at": r["asserted_at"].isoformat(),
                               "reason": "known_later" if r["known_at"] > t else "not_in_force"})
        out.append({"id": q.get("id", i), "asked_at": t.isoformat(), "evidence": len(q.get("evidence", [])), "leaked": leaked, "missing": missing})
    n = len(out)
    bad = sum(1 for q in out if q["leaked"])
    return {"questions": n, "leaked_questions": bad, "leak_rate": round(bad / n, 4) if n else 0.0,
            "leaked_blocks": sum(len(q["leaked"]) for q in out), "missing_blocks": sum(len(q["missing"]) for q in out), "per_question": out}
