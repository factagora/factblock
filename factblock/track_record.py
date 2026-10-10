"""Track records: how the claims, predictions and commitments in a bundle turned out, as known on a given day,
and which of them were on record before they were resolved.

    r = factblock.track_record("brain/", as_of="2026-07-01", by="speaker")
    r["groups"]      # per speaker: judged, right, wrong, mixed, open, overdue, hit_rate
    r["record"]      # before it was resolved: written then, written later from a cited source, written later on the writer's word

A statement counts once, by its latest verdict known on as_of. hit_rate is right / (right + wrong); mixed (partial,
misleading) and undecidable verdicts are counted but left out of it. open is a prediction or commitment with no
verdict yet; overdue, one past its due date with none.

On record before it was resolved: a row is written when its batch was captured (SPEC 6), or at its known_at when the
ledger stamped it live. Written by the verdict's decided_at, the statement was on record before it was judged.
Written later, it was backfilled after the fact: a cited source (a dated recording, an article) can still show it
was said first, and anyone can check it; with no source it rests on the writer's word, and hindsight is not ruled
out. A verdict can come after the outcome itself, so this is the floor of what a track record can show, not more."""
from __future__ import annotations

from .bundle import Bundle, BundleLike, Instant, parse_instant
from .recall import recall
from .scan import _as_of
from .timeline import _day, _outcome, _url

OPEN_KINDS = ("prediction", "commitment")


def track_record(bundle: BundleLike, as_of: Instant, *, by: str | None = None, ids: list[str] | None = None,
                 speaker: str | None = None) -> dict:
    """Use to see how statements turned out, as known on as_of: per group (a payload field such as speaker, or
    kind) how many were judged right, wrong or mixed, how many are open or overdue, and the hit rate; plus how many were
    on record before they were resolved. Pass `ids` (say, what a search found) to count only those statements: the
    record of calls like the one in front of you, rather than of everything. `speaker` keeps one speaker's.
    Returns {"as_of", "by", "groups", "total", "record", "left_out", "items", "certificate"}; left_out counts picked
    statements that are neither judged nor a prediction or commitment (a claim nobody has judged)."""
    b = bundle if isinstance(bundle, Bundle) else Bundle(bundle)
    t = _as_of(as_of)
    want = set(ids) if ids else None
    if want:
        missing = want - {n["id"] for n in b.nodes if n["known_at"] <= t}
        if missing:
            raise ValueError(f"not in the bundle as of {_day(t)}: {', '.join(sorted(missing))}")
    latest = {}
    for v in sorted((v for v in b.resolutions if v["known_at"] <= t), key=lambda v: (v["decided_at"], v["known_at"])):
        latest[v["target_id"]] = v
    captured = {k: parse_instant(d["captured_at"]) for k, d in b.backfills.items() if d.get("captured_at")}
    items, left_out = [], 0
    for n in b.nodes:
        p = n.get("payload") or {}
        if n["known_at"] > t or (want and n["id"] not in want) or (speaker and str(p.get("speaker", "")).casefold() != speaker.casefold()):
            continue
        v = latest.get(n["id"])
        if not (v or n["kind"] in OPEN_KINDS):
            left_out += 1 if want else 0
            continue
        o = str((v.get("outcome") or v.get("value")) if v else "")
        due = n.get("valid_to") if n["kind"] in OPEN_KINDS else None
        status = ("overdue" if due and due < t else "open") if not v else "undecidable" if o == "undecidable" else _outcome(o)
        written = n["known_at"]
        cap = captured.get((n.get("attestation") or {}).get("batch"))
        if cap is not None:
            written = max(written, cap)
        record = None
        if v:
            record = "before" if written <= v["decided_at"] else "sourced" if _url(p) else "writer"
        items.append({"id": n["id"], "kind": n["kind"], "statement": n.get("statement"), "said": _day(n["asserted_at"]),
                      "group": str(p.get(by, n.get(by)) or "other") if by else None, "status": status,
                      "verdict": o or None, "decided": _day(v["decided_at"]) if v else None, "written": _day(written),
                      "record": record, "source": _url(p)})
    items.sort(key=lambda i: (i["said"], i["id"]))

    def tally(rows):
        c = {k: sum(1 for i in rows if i["status"] == k) for k in ("right", "wrong", "mixed", "undecidable", "open", "overdue")}
        judged = len(rows) - c["open"] - c["overdue"]
        return {"judged": judged, **c, "hit_rate": round(c["right"] / (c["right"] + c["wrong"]), 3) if c["right"] + c["wrong"] else None}

    groups = {}
    for i in items:
        groups.setdefault(i["group"], []).append(i)
    record = {k: sum(1 for i in items if i["record"] == k) for k in ("before", "sourced", "writer")}
    return {"as_of": t.isoformat(), "by": by,
            "groups": [{"group": g, **tally(rows)} for g, rows in sorted(groups.items(), key=lambda x: str(x[0]))] if by else [],
            "total": tally(items), "record": record, "left_out": left_out, "items": items,
            "certificate": recall(b, "", as_of, limit=0)["certificate"]}
