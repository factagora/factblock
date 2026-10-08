"""SPEC 9: the ClaimReview projection. Every verdict visible as of an instant becomes one schema.org
ClaimReview (JSON-LD), the shape Google's fact-check tools, Meta's programme and ClaimReview-aware
CMSs consume. Lossy by design: one verdict per block (the latest), no chain, no interval. What
ClaimReview cannot say travels under `factblock:` keys that a consumer may ignore."""
from .bundle import Bundle, parse_instant
from .scan import _as_of, _visible, scan

#  outcome -> (alternateName, ratingValue on a 1..5 scale, or None when the scale does not apply)
RATINGS = {
    "true": ("True", 5), "mostly_true": ("Mostly true", 4), "mostly_false": ("Mostly false", 2), "false": ("False", 1),
    "misleading": ("Misleading", 2), "unverifiable": ("Unverifiable", None),
    "came_true": ("Came true", 5), "partial": ("Partially came true", 3), "did_not": ("Did not come true", 1), "undecidable": ("Undecidable", None),
}


def _actor(a):
    if not a:
        return None
    name = a.split(":", 1)[1] if a.startswith(("human:", "process:", "org:")) else a.split("/", 1)[0]
    return {"@type": "Person" if a.startswith("human:") else "Organization", "name": name}


def _rating(r):
    outcome = r.get("outcome") or (r["value"] if isinstance(r.get("value"), str) else None)
    name, value = RATINGS.get(outcome, (str(outcome) if outcome is not None else str(r.get("value")), None))
    out = {"@type": "Rating", "alternateName": name}
    if value is not None:
        out.update({"ratingValue": value, "bestRating": 5, "worstRating": 1})
    return out


def to_claimreview(bundle, as_of, base_url=None, valid_at=None) -> dict:
    """Use to publish verdicts: the ones visible as of an instant as schema.org ClaimReview JSON-LD (SPEC 9.2)."""
    b = bundle if isinstance(bundle, Bundle) else Bundle(bundle)
    s = scan(b, as_of, valid_at)
    t = _as_of(as_of); v = parse_instant(valid_at) if valid_at else t
    nodes = {n["id"]: n for n in b.nodes}
    latest = {}
    for r in sorted((r for r in b.resolutions if _visible(r, t, v)), key=lambda r: (r["decided_at"], r["known_at"])):
        latest[r["target_id"]] = r          # ClaimReview has no history: the latest verdict stands for the block
    reviews = []
    for tid, r in latest.items():
        n = nodes.get(tid)
        if n is None:
            continue
        payload = n.get("payload") or {}
        source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
        claim = {"@type": "Claim", "datePublished": n["asserted_at"].date().isoformat()}
        if payload.get("speaker"):
            claim["author"] = {"@type": "Person", "name": payload["speaker"]}
        elif n.get("author"):
            claim["author"] = _actor(n["author"])
        if source.get("url"):
            claim["appearance"] = {"@type": "CreativeWork", "url": source["url"], **({"name": source["title"]} if source.get("title") else {})}
        cr = {"@type": "ClaimReview", "claimReviewed": n.get("statement"), "datePublished": r["decided_at"].date().isoformat(),
              "itemReviewed": claim, "reviewRating": _rating(r), "factblock:id": tid, "factblock:kind": n["kind"],
              "factblock:known_at": r["known_at"].isoformat()}
        if _actor(r.get("resolver")):
            cr["author"] = _actor(r["resolver"])
        if base_url:
            cr["url"] = f"{base_url.rstrip('/')}/{tid}"
        if r.get("method"):
            cr["factblock:method"] = r["method"]
        reviews.append(cr)
    return {"@context": "https://schema.org", "@graph": reviews, "factblock:certificate": s.certificate}
