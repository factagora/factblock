"""Hindsight check for an eval set. Each question says when it was asked and which blocks its
answer rests on; a block the system learned after that instant is a leak. Same visibility rule
as scan (SPEC 4.1), so a leak-free question set is one every answer could have been given then."""
import json
from datetime import date, datetime
from pathlib import Path

from .bundle import Bundle, parse_instant
from .scan import _visible


def _questions(q):
    if isinstance(q, (str, Path)):
        return [json.loads(l) for l in Path(q).read_text().splitlines() if l.strip()]
    return list(q)


def _day_only(v):
    return (isinstance(v, date) and not isinstance(v, datetime)) or (isinstance(v, str) and len(v.strip()) == 10)


def _asked(v):
    """A question asked on a date could have been asked at its first moment, so a date-only asked_at is the
    start of that day in UTC: a block learned later that day is a leak. Reads (scan, recall) take the end of
    the day instead; for an eval gate the strict end is the safe one. Give a full timestamp to be exact, and pass
    the same timestamp to the reads that built the agent's context."""
    if isinstance(v, date) and not isinstance(v, datetime):
        v = v.isoformat()
    return parse_instant(v)


def leak(bundle, questions) -> dict:
    """questions: a JSONL path or dicts of {id?, asked_at, evidence: [block id, ...]}. A date-only asked_at
    means the start of that day (UTC), so a block learned later that day counts as a leak. A question without
    asked_at or an evidence list raises ValueError; ids the bundle lacks are listed under `missing`.
    `leaked_blocks` counts citations (a block cited by two leaking questions counts twice); each question
    carries `day_only` when its asked_at had no time."""
    b = bundle if isinstance(bundle, Bundle) else Bundle(bundle)
    rows = {r["id"]: r for r in b.nodes}
    out = []
    for i, q in enumerate(_questions(questions)):
        # a question without these would pass as leak-free, which is the wrong answer for an eval gate
        if "asked_at" not in q or not isinstance(q.get("evidence"), list):
            raise ValueError(f"question {q.get('id', i)} needs asked_at and evidence: [block id, ...]; got keys {sorted(q)}")
        t = _asked(q["asked_at"])
        v = parse_instant(q["valid_at"]) if q.get("valid_at") else t
        leaked, missing = [], []
        for nid in q["evidence"]:
            r = rows.get(nid)
            if r is None:
                missing.append(nid)
            elif not _visible(r, t, v):
                leaked.append({"id": nid, "known_at": r["known_at"].isoformat(), "asserted_at": r["asserted_at"].isoformat(),
                               "reason": "known_later" if r["known_at"] > t else "not_in_force"})
        out.append({"id": q.get("id", i), "asked_at": t.isoformat(), "day_only": _day_only(q["asked_at"]), "evidence": len(q["evidence"]), "leaked": leaked, "missing": missing})
    n = len(out)
    bad = sum(1 for q in out if q["leaked"])
    return {"questions": n, "leaked_questions": bad, "leak_rate": round(bad / n, 4) if n else 0.0,
            "leaked_blocks": sum(len(q["leaked"]) for q in out), "missing_blocks": sum(len(q["missing"]) for q in out), "per_question": out}
