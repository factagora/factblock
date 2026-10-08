"""SPEC 4.4: one value for one declared fact, by the declared policy, or a refusal with every
candidate attached. Mirrors tckg.resolve() so a file and the ledger answer the same."""
from datetime import datetime, timezone

from .bundle import Bundle, BundleLike, Instant, parse_instant
from .scan import _as_of


def _declaration(b, fact_key, at):
    """The declaration in force at `at`: latest declared_at <= at (declarations are as-of'd too)."""
    cands = [f for f in b.facts.get(fact_key, []) if f["declared_at"] <= at]
    return max(cands, key=lambda f: f["declared_at"]) if cands else None


def _covers(r, at):
    to = r.get("valid_to")
    return r["valid_from"] <= at and (to is None or at < to)


def resolve(bundle: BundleLike, fact_key: str, as_of: Instant, valid_at: Instant | None = None,
            rules_as_of: Instant | None = None) -> dict:
    """Use when one value is needed for a declared fact (a price, a stance): the value its declared policy
    picks as of an instant, or no_answer with a reason and every candidate. Never a guess (SPEC 4.4)."""
    if as_of is None:
        raise ValueError("as_of has no default: every read says which instant it asks about, e.g. as_of='2024-05-01' (SPEC 4.1)")
    b = bundle if isinstance(bundle, Bundle) else Bundle(bundle)
    t = _as_of(as_of)
    v = parse_instant(valid_at) if valid_at else t
    rules_at = parse_instant(rules_as_of) if rules_as_of else t

    all_rows = [n for n in b.nodes if n.get("fact_key") == fact_key]
    shown = [n for n in all_rows if n["known_at"] <= t]
    cert = {"fact": fact_key, "as_of": t.isoformat(), "valid_at": v.isoformat(), "read_at": datetime.now(timezone.utc).isoformat()}
    if len(all_rows) > len(shown):
        cert["masked"] = {"node": len(all_rows) - len(shown)}
    if rules_as_of and rules_at != t:
        cert["rules_as_of"] = rules_at.isoformat()

    def answer(status, value=None, reason=None, since=None, cands=(), policy=None):
        return {"status": status, "value": value, "reason": reason, "unresolved_since": since,
                "candidates": [{"id": c["id"], "value": c.get("fact_value"), "source": (c.get("payload") or {}).get("source"),
                                "valid_from": c["valid_from"].isoformat(), "valid_to": c["valid_to"].isoformat() if c.get("valid_to") else None,
                                "known_at": c["known_at"].isoformat()} for c in cands],
                "policy": policy, "certificate": cert}

    decl = _declaration(b, fact_key, rules_at)
    if decl is None:
        return answer("no_answer", reason="undeclared_fact")
    policy = decl.get("policy", "latest_valid")

    cands = sorted([n for n in shown if _covers(n, v)], key=lambda n: (n["known_at"], n["id"]))
    batches = {n["attestation"]["batch"] for n in cands if n.get("attestation", {}).get("batch")}
    if batches:
        cert["backfill"] = {"batches": len(batches), "rows": sum(1 for n in cands if n.get("attestation", {}).get("batch"))}

    if not cands:
        reason = "no_data" if not all_rows else "not_yet" if not shown else "no_value_at"
        return answer("no_answer", reason=reason, policy=policy)
    if len(cands) == 1:
        return answer("answered", value=cands[0].get("fact_value"), cands=cands, policy=policy)

    if policy == "strict":
        return answer("no_answer", reason="unresolved_conflict", since=cands[1]["known_at"].isoformat(), cands=cands, policy=policy)
    if policy == "latest_valid":
        rank = lambda n: n["valid_from"]  # noqa: E731
        eligible = cands
    elif policy == "latest_observed":
        rank = lambda n: n["known_at"]  # noqa: E731
        eligible = cands
    else:  # source_priority: a declared order, never a blended score; an unranked source is nowhere
        order = decl.get("source_order") or []
        eligible = [n for n in cands if (n.get("payload") or {}).get("source") in order]
        rank = lambda n: -order.index((n.get("payload") or {}).get("source"))  # noqa: E731
    if eligible:
        top = max(rank(n) for n in eligible)
        winners = [n for n in eligible if rank(n) == top]
    else:
        winners = []
    if len(winners) != 1:
        return answer("no_answer", reason="unresolved_conflict", since=cands[1]["known_at"].isoformat(), cands=cands, policy=policy)
    return answer("answered", value=winners[0].get("fact_value"), cands=cands, policy=policy)
