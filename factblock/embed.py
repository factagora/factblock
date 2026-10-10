"""Meaning for recall: an embed function, and statement vectors cached beside the bundle.

    embed = factblock.embedder("gemini")                  # or "openai"; any fn(list[str]) -> list[list[float]] works
    factblock.recall("brain/", "what does it cost?", as_of="2026-04-10", embed=embed)

A vector is a search index, not part of the record: it depends on the model, so the bundle stays complete without
one. Vectors the bundle carries are used when `declarations.embedding.model` names the same model as `embed.model`;
otherwise they are computed once and kept in `<bundle>/.factblock-cache/`, keyed by the statement's text, so a
second recall over the same bundle calls the model only for the question."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Callable

CACHE = ".factblock-cache"


def embedder(provider: str = "gemini", model: str | None = None, dimensions: int | None = None) -> Callable[[list[str]], list[list[float]]]:
    """An embed function for recall(embed=...), with `.model` naming what it computes (used for the cache).
    gemini: gemini-embedding-001 (GEMINI_API_KEY, or GOOGLE_GENAI_USE_VERTEXAI=1 with GOOGLE_CLOUD_PROJECT); pip install 'factblock[gemini]'.
    openai: text-embedding-3-small (OPENAI_API_KEY); pip install 'factblock[openai]'."""
    if provider == "gemini":
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise ImportError("embedder 'gemini' needs the Gemini SDK: pip install 'factblock[gemini]'") from None
        client, model = genai.Client(), model or "gemini-embedding-001"
        config = types.EmbedContentConfig(output_dimensionality=dimensions) if dimensions else None

        def one(texts):
            r = client.models.embed_content(model=model, contents=texts, config=config)
            return [list(e.values) for e in r.embeddings]

        def fn(texts):
            out = []
            for i in range(0, len(texts), 100):
                chunk = texts[i:i + 100]
                try:
                    out += one(chunk)
                except Exception:   # some endpoints take one text per request (Vertex gemini-embedding-001)
                    out += [one([t])[0] for t in chunk]
            return out
    elif provider == "openai":
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("embedder 'openai' needs the OpenAI SDK: pip install 'factblock[openai]'") from None
        client, model = OpenAI(), model or "text-embedding-3-small"
        extra = {"dimensions": dimensions} if dimensions else {}

        def fn(texts):
            out = []
            for i in range(0, len(texts), 1000):
                out += [d.embedding for d in client.embeddings.create(model=model, input=texts[i:i + 1000], **extra).data]
            return out
    else:
        raise ValueError(f"unknown embedder {provider!r}: use 'gemini' or 'openai', or pass your own fn(list[str]) -> list[list[float]]")
    fn.model = f"{provider}:{model}" + (f":{dimensions}" if dimensions else "")
    return fn


def _key(text):
    return hashlib.sha1(text.encode()).hexdigest()


def vectors(bundle, nodes, embed) -> dict[str, list[float]]:
    """A vector per node id: the bundle's own when it declares the same model, else cached or computed now."""
    model = getattr(embed, "model", None)
    declared = ((bundle.manifest.get("declarations") or {}).get("embedding") or {}).get("model")
    out = {n["id"]: n["embedding"] for n in nodes if model and declared == model and n.get("embedding")}
    todo = [n for n in nodes if n["id"] not in out and (n.get("statement") or "").strip()]
    path = Path(bundle.path) / CACHE / f"embeddings-{re.sub(r'[^A-Za-z0-9_.-]', '_', model)}.json" if model else None
    cache = json.loads(path.read_text()) if path and path.exists() else {}
    missing = sorted({n["statement"] for n in todo if _key(n["statement"]) not in cache})
    if missing:
        for text, v in zip(missing, embed(missing)):
            cache[_key(text)] = v
        if path:
            path.parent.mkdir(exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(cache))
            os.replace(tmp, path)
    out.update({n["id"]: cache[_key(n["statement"])] for n in todo})
    return out


def cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = sum(x * x for x in a) ** 0.5, sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0
