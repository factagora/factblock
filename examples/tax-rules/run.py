"""Twelve tax questions a CPA firm gets, three ways to answer them with the same model and the same rules.

    python examples/tax-rules/run.py              # deterministic part only: what FactBlock picks, no model
    python examples/tax-rules/run.py --llm        # also ask a model three ways (Gemini; GEMINI_API_KEY or Vertex)
    python examples/tax-rules/run.py --llm --json

The rules are public U.S. tax law that changed over time (rules.csv, every row links to its source):
bonus depreciation (changed retroactively, and only for property acquired after a date), research costs
(domestic and foreign treated differently), a retroactive election with a deadline, BOI reporting (on, off,
on, off, on, then gone for U.S. companies), and a disaster postponement that covers one county.

  model only     the question, nothing else
  vector RAG     the four rows closest in meaning to the question, as most retrieval stacks do (time-blind)
  FactBlock      the rows that apply to this client (applies_if), read as of the day asked (as_of)
                 for the day the question is about (valid_at), replacements marked

Every arm gets the same question, the same date ("today is ..."), and multiple-choice options, so scoring
is exact. The FactBlock arm also prints the answer it would give without any model: the most specific
row in force, with its source."""
import csv
import datetime as dt
import json
import re
import sys
import tempfile
from pathlib import Path

import factblock

HERE = Path(__file__).resolve().parent
ROWS = list(csv.DictReader((HERE / "rules.csv").open()))
QUESTIONS = [json.loads(l) for l in (HERE / "questions.jsonl").open() if l.strip()]


def applies(row, facts):
    """applies_if is `key=value`, `key_after=date` or `key_before=date`, joined by ';'. A row whose
    condition names a fact the client does not have does not apply to that client.
    shortcut: conditions live in the payload and are checked here, before the bundle is read; upgrade to a
    SPEC field once conditional replacement (a row replaces another only for some clients) is in the format."""
    for cond in filter(None, row["applies_if"].split(";")):
        key, want = cond.split("=")
        if key.endswith("_after") or key.endswith("_before"):
            have = facts.get(key.rsplit("_", 1)[0])
            if have is None or (have <= want if key.endswith("_after") else have >= want):
                return False
        elif facts.get(key) != want:
            return False
    return True


_views = {}


def view(facts):
    """The client's own bundle: only rows that apply to them, so a replacement that only covers other
    clients does not mark this client's rule as replaced."""
    key = json.dumps(facts, sort_keys=True)
    if key not in _views:
        mine = [r for r in ROWS if applies(r, facts)]
        ids = {r["id"] for r in mine}
        recs = []
        for r in mine:
            rec = {k: v for k, v in r.items() if v and k not in ("applies_if", "replaces")}
            if r["replaces"] in ids:
                rec["replaces"] = r["replaces"]
            rec["conditions"] = str(len([c for c in r["applies_if"].split(";") if c]))
            recs.append(rec)
        out = Path(tempfile.mkdtemp(prefix="tax-")) / "brain"
        factblock.write_bundle(factblock.from_records(recs, backfill=True), out)
        _views[key] = out
    return _views[key]


def factblock_read(q):
    b = view(q["facts"])
    r = factblock.recall(b, q["query"], as_of=q["asked_at"], valid_at=q["valid_at"], limit=6)
    # the deterministic answer: rows in force and not replaced, the most specific first, then the newest said
    live = [i for i in r["items"] if not i.get("superseded_by")]
    payload = {n["id"]: n.get("payload") or {} for n in factblock.Bundle(b).nodes}
    live = [i for i in live if payload[i["id"]].get("value") and not payload[i["id"]].get("based_on")]
    live.sort(key=lambda i: (-int(payload[i["id"]].get("conditions", 0)), -i["asserted_at"].timestamp()))
    pick = live[0] if live else None
    text = factblock.context(b, q["query"], as_of=q["asked_at"], valid_at=q["valid_at"], limit=6)
    return {"value": payload[pick["id"]]["value"] if pick else None, "row": pick and pick["id"],
            "source": pick and payload[pick["id"]].get("source"), "context": text}


def renotify(asked_at):
    """Advice the firm gave whose basis was replaced later, for the client it was given to."""
    out = []
    for m in (r for r in ROWS if r["based_on"]):
        facts = dict(c.split("=") for c in m["applies_if"].split(";") if c)
        facts |= {"acquired": "2025-02-10"} if facts.get("client") == "A" else {}   # the client's file
        r = factblock.recall(view(facts), "", as_of=asked_at, valid_at=m["effective_from"], limit=100)
        basis = next((i for i in r["items"] if i["id"] == m["based_on"]), None)
        if basis and basis.get("superseded_by"):
            out.append(f"{m['id']} ({m['said_at']}): {m['text']}\n    rests on {basis['id']}, replaced by "
                       f"{basis['superseded_by']['id']} (said {basis['superseded_by']['asserted_at'].date()}): {basis['superseded_by']['statement']}")
    return out


# --- the model arms -------------------------------------------------------------------------------

_genai = []


def _client():
    if not _genai:
        from google import genai
        _genai.append(genai.Client())
    return _genai[0]


def _embed(text):
    return _client().models.embed_content(model="gemini-embedding-001", contents=[text]).embeddings[0].values


def vector_rag(q, k=4):
    """Time-blind retrieval: embed every row once, take the k nearest to the question."""
    from factblock.embed import cosine
    cache = HERE / ".factblock-cache" / "vectors.json"   # gitignored, like recall's own cache
    vecs = json.loads(cache.read_text()) if cache.exists() else {}
    missing = [r for r in ROWS if r["id"] not in vecs]
    if missing:
        vecs |= {r["id"]: _embed(r["text"]) for r in missing}
        cache.parent.mkdir(exist_ok=True)
        cache.write_text(json.dumps(vecs))
    qv = _embed(q["question"])
    top = sorted(ROWS, key=lambda r: -cosine(qv, vecs[r["id"]]))[:k]
    return "\n".join(f"- {r['said_at']}: {r['text']} (source: {r['source']})" for r in top)


def ask(q, notes, model="gemini-2.5-flash"):
    from google.genai import types
    opts = "\n".join(f"{chr(65 + i)}. {o}" for i, o in enumerate(q["options"]))
    prompt = (f"Today is {q['asked_at']}. You are a tax assistant at a U.S. CPA firm.\n\n"
              + (f"Firm knowledge base notes:\n{notes}\n\n" if notes else "")
              + f"Question: {q['question']}\n\nOptions:\n{opts}\n\nReply with the letter of the best option only.")
    r = _client().models.generate_content(model=model, contents=prompt, config=types.GenerateContentConfig(temperature=0))
    text = (r.text or "").strip()
    # a bare letter, or the one a model that explains anyway marks: \boxed{X} or **X
    m = [x for t in re.findall(r"boxed\{([A-Z])\}|\*\*([A-Z])\b|^([A-Z])\b", text) for x in t if x]
    i = ord(m[-1]) - 65 if m else -1
    return q["options"][i] if 0 <= i < len(q["options"]) else text[:80]


def main():
    llm, as_json = "--llm" in sys.argv, "--json" in sys.argv
    today = dt.date.today().isoformat()
    res = []
    for q in QUESTIONS:
        fb = factblock_read(q)
        row = {"id": q["id"], "kind": q["kind"], "asked_at": q["asked_at"], "answer": q["answer"], "factblock_rule": fb}
        if llm:
            rag = vector_rag(q)
            row["model_only"] = ask(q, None)
            row["vector_rag"] = ask(q, rag)
            row["factblock_llm"] = ask(q, fb["context"])
            row["rag_context"] = rag
        res.append(row)
    if as_json:
        print(json.dumps({"results": res, "renotify": renotify(today)}, indent=1, default=str))
        return
    arms = ["factblock_rule"] + (["model_only", "vector_rag", "factblock_llm"] if llm else [])
    got = lambda r, a: r[a]["value"] if a == "factblock_rule" else r[a]   # noqa: E731
    for r in res:
        print(f"\n{r['id']}  asked {r['asked_at']}  {r['kind']}\n    right answer: {r['answer']}")
        for a in arms:
            ok = got(r, a) == r["answer"]
            extra = f"   [{r[a]['row']}: {r[a]['source']}]" if a == "factblock_rule" else ""
            print(f"    {a:<15} {'ok   ' if ok else 'WRONG'} {got(r, a)}{extra}")
    n = len(res)
    print("\n" + ", ".join(f"{a} {sum(got(r, a) == r['answer'] for r in res)}/{n}" for a in arms))
    print(f"\nadvice to re-send as of {today}:")
    print("\n".join("  " + x for x in renotify(today)) or "  none")


if __name__ == "__main__":
    main()
