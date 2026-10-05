"""Fact-check feeds -> FactBlock bundle (SPEC 9.2, reverse direction). Reads the shape of Google's
Fact Check Tools API (claims:search): a claim with `text`, `claimant`, `claimDate` and its
`claimReview[]` with `publisher`, `url`, `title`, `reviewDate`, `textualRating`. Each claim becomes a
node, each review a resolution row. The feed's dates are self-reported, so every row is written
under a backfill batch declared at its review date (section 6): the claim became known to the
fact-checking world when it was first reviewed, and each verdict when it was published.

    bundle_from_factcheck(claims, existing=None) -> {"manifest", "nodes", "edges", "resolutions"}
    search(query, api_key, language=None, pages=1)  -> claims   # the live API; needs a Google API key
"""
import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from ..bundle import parse_instant

LEDGER = "factblock-factcheck-adapter/0.1"
API = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
#  textualRating, lowercased and stripped of punctuation -> recommended outcome (SPEC 3.6). Unknown ratings keep value only.
OUTCOMES = {"true": "true", "correct": "true", "accurate": "true", "mostly true": "mostly_true", "mostly correct": "mostly_true",
            "partly true": "mostly_true", "partially true": "mostly_true", "half true": "misleading", "misleading": "misleading",
            "missing context": "misleading", "mostly false": "mostly_false", "partly false": "mostly_false", "false": "false",
            "incorrect": "false", "pants on fire": "false", "fake": "false", "unproven": "unverifiable", "unverifiable": "unverifiable",
            "unsupported": "unverifiable", "no evidence": "unverifiable"}


def _iso(v):
    d = parse_instant(v)
    return d.astimezone(timezone.utc).isoformat()


def _outcome(rating):
    key = "".join(c if c.isalnum() or c == " " else " " for c in (rating or "").lower()).split()
    return OUTCOMES.get(" ".join(key))


def search(query, api_key, language=None, pages=1, page_size=100):
    """claims:search, following nextPageToken up to `pages` times. Returns the raw claim dicts."""
    out, token = [], None
    for _ in range(pages):
        q = {"query": query, "key": api_key, "pageSize": page_size, **({"languageCode": language} if language else {}), **({"pageToken": token} if token else {})}
        try:
            with urllib.request.urlopen(API + "?" + urllib.parse.urlencode(q), timeout=60) as resp:
                d = json.load(resp)
        except urllib.error.HTTPError as e:      # Google puts the reason in the body; show it instead of a bare status
            body = e.read().decode(errors="replace")
            try:
                body = json.loads(body)["error"]["message"]
            except (ValueError, KeyError, TypeError):
                pass
            raise RuntimeError(f"Fact Check Tools API: HTTP {e.code}: {body}") from None
        out += d.get("claims", [])
        token = d.get("nextPageToken")
        if not token:
            break
    return out


def bundle_from_factcheck(claims, existing=None, namespace="factcheck", captured_at=None) -> dict:
    captured_at = _iso(captured_at or datetime.now(timezone.utc))
    have_nodes = {n["id"] for n in (existing.nodes if existing else [])}
    have_res = {(r["target_id"], r["decided_at"].isoformat()) for r in (existing.resolutions if existing else [])}
    batches, nodes, resolutions = {}, [], []

    def stamp(at):
        batches.setdefault(at, f"factcheck-{at[:10]}-{hashlib.sha1(at.encode()).hexdigest()[:6]}")
        return {"known_at": at, "attestation": {"ledger": LEDGER, "batch": batches[at]}}

    for c in claims:
        reviews = [r for r in c.get("claimReview", []) if r.get("reviewDate")]
        if not c.get("text") or not reviews:
            continue
        reviews.sort(key=lambda r: r["reviewDate"])
        first = _iso(reviews[0]["reviewDate"])
        asserted = _iso(c["claimDate"]) if c.get("claimDate") else first
        nid = hashlib.sha1(f"{c['text']}|{c.get('claimant', '')}|{asserted}".encode()).hexdigest()[:16]
        if nid not in have_nodes:
            have_nodes.add(nid)
            payload = {"language": reviews[0].get("languageCode")}
            if c.get("claimant"):
                payload["speaker"] = c["claimant"]
            nodes.append({"id": nid, "kind": "claim", "statement": c["text"], "payload": {k: v for k, v in payload.items() if v},
                          "asserted_at": asserted, "valid_from": asserted, "valid_to": None, **stamp(first)})
        for r in reviews:
            decided = _iso(r["reviewDate"])
            if (nid, decided) in have_res:
                continue
            have_res.add((nid, decided))
            pub = r.get("publisher") or {}
            row = {"target_id": nid, "value": r.get("textualRating"), "method": "claimreview", "decided_at": decided, **stamp(decided),
                   "evidence": [{"type": "FACT_CHECK", "url": r.get("url"), "title": r.get("title"), "publisher": pub.get("name"), "published_at": decided}]}
            if pub.get("site"):
                row["resolver"] = f"org:{pub['site']}"
            if _outcome(r.get("textualRating")):
                row["outcome"] = _outcome(r["textualRating"])
            resolutions.append(row)
    manifest = {"factblock_version": "1.0-draft.1", "namespace": namespace, "source": LEDGER, "exported_as_of": captured_at,
                "tables": {"nodes": "nodes.jsonl", "edges": "edges.jsonl", "resolutions": "resolutions.jsonl"},
                "declarations": {"facts": [], "edge_types": [], "embedding": None,
                                 "backfills": [{"batch": name, "declared_known_at": at, "reason": "fact-check feed: the publisher's review date is self-reported",
                                                "declared_by": "process:" + LEDGER, "captured_at": captured_at} for at, name in sorted(batches.items())]}}
    return {"manifest": manifest, "nodes": nodes, "edges": [], "resolutions": resolutions,
            "summary": {"claims": len(nodes), "verdicts": len(resolutions), "batches": len(batches)}}
