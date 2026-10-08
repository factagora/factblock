"""Text in, blocks out: the claims profile (factblock/profiles/claims) run through a model
the caller chooses, written as a bundle this library can read back.

    extract(text, observed_at, speaker=..., provider="gemini"|"openai"|"fake") -> {"manifest", "nodes", "edges"}
    write_bundle(result, out, append=True)                                     # bundle.py

The profile is three files, not code: instructions.md (the rules), output.schema.json (what the
model returns), edge-types.json (the link types and their families). Any language can run the
same extraction by reading them; this module is the Python one. tckg runs the same profile
on its side, so a block extracted here and a block extracted there are the same shape.

A writer that is not a ledger must not invent known_at (SPEC 6). Every extract declares one
backfill batch: known_at is the instant you say you learned this (default: now), attested by
"process:factblock-extract", and the batch record keeps the real capture instant.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .bundle import Bundle, parse_instant

LEDGER = "factblock-extract/0.1"
PROFILE = Path(__file__).parent / "profiles" / "claims"


def load_profile(name: str = "claims") -> dict:
    d = Path(__file__).parent / "profiles" / name
    return {"instructions": (d / "instructions.md").read_text(),
            "schema": json.loads((d / "output.schema.json").read_text()),
            "edge_types": json.loads((d / "edge-types.json").read_text())}


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# --- providers: one function each, same signature, JSON out ----------------------

def _prompt(profile, text, observed_at, speaker, source):
    head = [f"Reference time (the only today you know): {_iso(observed_at)}"]
    if speaker:
        head.append(f"Speaker: {speaker}")
    if source:
        head.append(f"Source: {source}")
    return "\n".join(head) + "\n\n<text>\n" + text + "\n</text>"


def _gemini(profile, user, model):
    try:
        from google import genai  # GEMINI_API_KEY, or GOOGLE_GENAI_USE_VERTEXAI=1 + GOOGLE_CLOUD_PROJECT
        from google.genai import types
    except ImportError:
        raise ImportError("provider 'gemini' needs the Gemini SDK: pip install 'factblock[gemini]'; or provider='fake' to try the format without a model") from None
    client = genai.Client()
    cfg = dict(system_instruction=profile["instructions"], response_mime_type="application/json", temperature=0.2,
               automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))  # no tools here; silences the SDK's AFC notice
    try:
        config = types.GenerateContentConfig(response_json_schema=profile["schema"], **cfg)
    except Exception:  # older SDKs: the instructions carry the shape
        config = types.GenerateContentConfig(**cfg)
    r = client.models.generate_content(model=model or "gemini-2.5-pro", contents=user, config=config)
    return json.loads(r.text)


def _openai(profile, user, model):
    try:
        from openai import OpenAI  # OPENAI_API_KEY, OPENAI_BASE_URL for compatible servers
    except ImportError:
        raise ImportError("provider 'openai' needs the OpenAI SDK: pip install 'factblock[openai]'; or provider='fake' to try the format without a model") from None
    client = OpenAI()
    r = client.chat.completions.create(
        model=model or "gpt-4o-mini", temperature=0.2,
        messages=[{"role": "system", "content": profile["instructions"]}, {"role": "user", "content": user}],
        response_format={"type": "json_schema", "json_schema": {"name": "factblock_extract", "schema": profile["schema"]}})
    return json.loads(r.choices[0].message.content)


def _fake(profile, user, model):
    """No model. Each sentence is a block, consecutive blocks are linked by CAUSES, capitalized
    words that are not sentence starts are entities. For tests and offline runs."""
    text = user.split("<text>\n", 1)[1].rsplit("\n</text>", 1)[0]
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    blocks = [{"ref": f"b{i + 1}", "kind": "prediction" if re.search(r"\b(will|keep|going to|by \w+ end)\b", s, re.I) else "claim",
               "statement": s.rstrip("."), "speaker": "unknown", "quote": s, "confidence": 0.7, "topics": ["other"]}
              for i, s in enumerate(sents)]
    names = {}
    for b in blocks:
        for m in re.finditer(r"(?<!^)(?<![.!?]\s)\b([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)*)\b", b["statement"]):
            names.setdefault(m.group(1), set()).add(b["ref"])
    entities = [{"name": n, "type": "other", "mentioned_by": sorted(refs)} for n, refs in names.items()]
    links = [{"source": blocks[i]["ref"], "target": blocks[i + 1]["ref"], "type": "CAUSES", "confidence": 0.6}
             for i in range(len(blocks) - 1)]
    return {"blocks": blocks, "entities": entities, "links": links}


PROVIDERS = {"gemini": _gemini, "openai": _openai, "fake": _fake}


# --- extraction -----------------------------------------------------------------

def extract(text: str, observed_at, *, speaker: str | None = None, source: str | None = None,
            provider: str = "gemini", model: str | None = None, known_at=None, backfill: bool = False,
            declared_by: str | None = None, namespace: str = "local", existing: Bundle | None = None) -> dict:
    """Run the claims profile over `text` and return a bundle as plain dicts. `observed_at` is when the
    text was said or written: every block is asserted then. `known_at` is when you learned it (default
    now), declared as one backfill batch; `backfill=True` sets it to `observed_at`, the usual choice for
    material from the past ("treat it as known when it was said"). `existing` lets entities reuse ids
    already in a bundle."""
    if provider not in PROVIDERS:
        raise ValueError(f"provider must be one of {', '.join(sorted(PROVIDERS))}; got {provider!r}")
    profile = load_profile()
    observed_at = parse_instant(observed_at)
    now = datetime.now(timezone.utc)
    known_at = parse_instant(known_at) if known_at else (observed_at if backfill else now)
    out = PROVIDERS[provider](profile, _prompt(profile, text, observed_at, speaker, source), model)

    batch = f"extract-{known_at.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
    stamp = {"known_at": _iso(known_at), "attestation": {"ledger": LEDGER, "batch": batch}}
    at = _iso(observed_at)
    author = f"human:{_slug(speaker)}" if speaker and speaker.lower() not in ("host", "guest", "unknown") else None

    nodes, edges, ids = [], [], {}
    for b in out.get("blocks", []):
        nid = uuid.uuid4().hex[:8]        # short enough to type into `why`; a folder is one writer's memory
        ids[b["ref"]] = nid
        horizon = b.get("horizon_days")
        payload = {k: b[k] for k in ("speaker", "quote", "confidence", "topics", "asset", "direction", "horizon_days") if b.get(k) not in (None, [], "")}
        if source:
            payload["source"] = source
        nodes.append({"id": nid, "kind": b["kind"], "statement": b["statement"], "payload": payload,
                      "asserted_at": at, "valid_from": at,
                      "valid_to": _iso(observed_at + timedelta(days=int(horizon))) if horizon else None,
                      **({"author": author} if author else {}), **stamp})

    known_entities = {n["statement"]: n["id"] for n in (existing.nodes if existing else []) if n.get("kind") == "entity"}
    for e in out.get("entities", []):
        name = e["name"].strip()
        if not name:
            continue
        eid = known_entities.get(name)
        if not eid:
            eid = known_entities[name] = uuid.uuid4().hex[:8]
            nodes.append({"id": eid, "kind": "entity", "statement": name, "payload": {"type": e.get("type", "other")},
                          "asserted_at": at, "valid_from": at, "valid_to": None, **stamp})
        for ref in e.get("mentioned_by", []):
            if ref in ids:
                edges.append({"source_id": ids[ref], "target_id": eid, "edge_type": "MENTIONS",
                              "asserted_at": at, "valid_from": at, "valid_to": None, **stamp})

    dropped = 0
    for l in out.get("links", []):
        if l["type"] not in profile["edge_types"] or l["source"] not in ids or l["target"] not in ids or l["source"] == l["target"]:
            dropped += 1
            continue
        row = {"source_id": ids[l["source"]], "target_id": ids[l["target"]], "edge_type": l["type"],
               "asserted_at": at, "valid_from": at, "valid_to": None, **stamp}
        if isinstance(l.get("confidence"), (int, float)):
            row["confidence"] = max(0.0, min(1.0, float(l["confidence"])))
        if l.get("lag"):
            row["properties"] = {"lag_text": l["lag"]}  # ponytail: the speaker's words; an ISO duration when something computes with it
        edges.append(row)

    manifest = {
        "factblock_version": "1.0-draft.1", "namespace": namespace, "source": LEDGER, "exported_as_of": _iso(now),
        "tables": {"nodes": "nodes.jsonl", "edges": "edges.jsonl"},
        "declarations": {"facts": [], "edge_types": [], "embedding": None,
                         "backfills": [{"batch": batch, "declared_known_at": _iso(known_at),
                                        "reason": f"factblock extract ({provider}) from {source or 'text'}",
                                        "declared_by": declared_by or f"process:{LEDGER}", "captured_at": _iso(now)}]},
    }
    return {"manifest": manifest, "nodes": nodes, "edges": edges,
            "summary": {"blocks": len(ids), "entities": len(out.get("entities", [])), "links": len(out.get("links", [])) - dropped,
                        "links_dropped": dropped, "batch": batch}}
