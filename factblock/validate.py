"""SPEC section 2: the five invariants, one check id each. No engine, no network."""
from dataclasses import dataclass
from datetime import datetime

from .bundle import Bundle

CORE_FAMILY = {
    "CAUSES": "causal", "CONTRIBUTING_FACTOR": "causal", "TRIGGERS": "causal", "PREVENTS": "causal",
    "SUPERSEDES": "temporal", "CONCURRENT_SIGNAL": "temporal", "RESTATES": "temporal",
    "SUPPORTS": "argumentative", "CONTRADICTS": "argumentative", "QUALIFIES": "argumentative",
    "DEPENDS_ON": "general", "DERIVED_FROM": "general", "MENTIONS": "general",
}
FAMILIES = {"causal", "temporal", "argumentative", "general"}
POLICIES = {"latest_valid", "latest_observed", "source_priority", "strict"}


@dataclass
class Check:
    check_id: str
    ok: bool
    detail: str


def _label(kind, r):
    return r.get("id") or f'{r.get("source_id")}->{r.get("target_id")}:{r.get("edge_type")}' if kind != "resolution" else f'resolution of {r.get("target_id")}'


def _overlap(a_from, a_to, b_from, b_to):
    a_to = a_to or datetime.max.replace(tzinfo=a_from.tzinfo)
    b_to = b_to or datetime.max.replace(tzinfo=b_from.tzinfo)
    return a_from < b_to and b_from < a_to


def _unique(rows, key, label):
    bad = []
    seen = {}
    for r in rows:
        k = key(r)
        for other in seen.get(k, []):
            if _overlap(r["valid_from"], r.get("valid_to"), other["valid_from"], other.get("valid_to")):
                bad.append(label(r))
        seen.setdefault(k, []).append(r)
    return bad


def validate(bundle) -> list[Check]:
    b = bundle if isinstance(bundle, Bundle) else Bundle(bundle)
    out = []

    def check(check_id, bad, what):
        out.append(Check(check_id, not bad, "ok" if not bad else f"{len(bad)} {what}: {', '.join(map(str, bad[:5]))}"))

    # I1 three clocks
    missing, misordered = [], []
    for kind, r in b.blocks():
        need = ("decided_at", "known_at") if kind == "resolution" else ("asserted_at", "valid_from", "known_at")
        if any(not isinstance(r.get(k), datetime) for k in need):
            missing.append(_label(kind, r))
        elif kind != "resolution" and r.get("valid_to") is not None and not r["valid_from"] < r["valid_to"]:
            misordered.append(_label(kind, r))
    check("I1.present", missing, "blocks missing a clock")
    check("I1.ordered", misordered, "blocks with valid_from >= valid_to")

    # I2 attested knowledge time
    unattested, nobatch, selfatt = [], [], []
    for kind, r in b.blocks():
        a = r.get("attestation") or {}
        if not a.get("ledger"):
            unattested.append(_label(kind, r))
            continue
        batch = a.get("batch")
        if batch is not None:
            bf = b.backfills.get(batch)
            if bf is None or r.get("known_at") != bf["declared_known_at"]:
                nobatch.append(_label(kind, r))
        if r.get("author") and r["author"] == a["ledger"]:
            selfatt.append(_label(kind, r))
    check("I2.attested", unattested, "blocks without attestation.ledger")
    check("I2.batch_exists", nobatch, "blocks whose batch is undeclared or whose known_at differs from the batch")
    check("I2.no_self", selfatt, "blocks attested by their own author")

    # I3 append only
    check("I3.node_unique", _unique(b.nodes, lambda r: r["id"], lambda r: r["id"]), "node ids with overlapping valid")
    check("I3.edge_unique", _unique(b.edges, lambda r: (r["source_id"], r["target_id"], r["edge_type"]),
                                     lambda r: _label("edge", r)), "edges with overlapping valid")

    # I4 typed edges
    unknown = [_label("edge", r) for r in b.edges if r.get("edge_type") not in CORE_FAMILY and r.get("edge_type") not in b.edge_types]
    badfam = [t for t, f in b.edge_types.items() if f not in FAMILIES]
    check("I4.known_type", unknown, "edges with an undeclared edge_type")
    check("I4.family_declared", badfam, "declared edge_types with an unknown family")

    # I5 declared facts
    undeclared = sorted({r["fact_key"] for r in b.nodes if r.get("fact_key") and r["fact_key"] not in b.facts})
    badpol = [k for k, fs in b.facts.items() if any(f.get("policy", "latest_valid") not in POLICIES for f in fs)]
    check("I5.declared", undeclared, "fact_keys used but not declared")
    check("I5.policy_known", badpol, "facts with an unknown policy")
    return out
