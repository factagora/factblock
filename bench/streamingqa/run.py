"""How much does a memory that ignores time leak? Measured on StreamingQA (DeepMind, CC-BY 4.0).

StreamingQA asks 36,378 questions during 2020 about news published 2007 to 2020, and every question's
evidence predates it. We turn each question's evidence into one dated block (known when the article was
published), then recall the top-k blocks for a sample of questions two ways:

  time-ignorant   recall over everything the memory holds today (as_of far in the future)
  as-of           recall as of the day the question was asked

The time-ignorant picks go into a question set and `factblock leak` counts how many questions rest on a
block learned after they were asked. The as-of run cannot leak by construction; its number is how many
blocks it had to hide to say so.

    uv run python bench/streamingqa/run.py [--questions 500] [--k 5] [--seed 0]
"""
import argparse
import datetime as dt
import gzip
import json
import pathlib
import random
import sys
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import factblock  # noqa: E402
from factblock.recall import recall  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE / "data"
URL = "https://storage.googleapis.com/dm-streamingqa/streaminqa_eval.jsonl.gz"
FAR = "2100-01-01"


def rows():
    DATA.mkdir(exist_ok=True)
    f = DATA / "streaminqa_eval.jsonl.gz"
    if not f.exists():
        print(f"downloading {URL} (7.5 MB)")
        urllib.request.urlretrieve(URL, f)
    with gzip.open(f, "rt") as fh:
        return [json.loads(l) for l in fh]


def iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat()


def bundle(qa):
    """One claim per question: the answer, dated by its evidence article; the question rides as the quote.
    known_at is the article date, declared as a backfill batch per distinct date (SPEC 6)."""
    out = DATA / "bundle"
    if (out / "factblock.json").exists():
        return out
    batches = {}
    nodes = []
    for r in qa:
        at = iso(r["evidence_ts"])
        batches.setdefault(at, f"wmt-{at[:10]}-{len(batches)}")
        nodes.append({"id": r["qa_id"], "kind": "claim", "statement": r["answers"][0], "payload": {"quote": r["question"], "source": {"published_at": at}},
                      "asserted_at": at, "valid_from": at, "valid_to": None, "known_at": at,
                      "attestation": {"ledger": "factblock-bench-streamingqa/0.1", "batch": batches[at]}})
    manifest = {"factblock_version": "1.0-draft.1", "namespace": "bench:streamingqa", "source": "factblock-bench-streamingqa/0.1",
                "tables": {"nodes": "nodes.jsonl", "edges": "edges.jsonl"},
                "declarations": {"facts": [], "edge_types": [], "embedding": None,
                                 "backfills": [{"batch": b, "declared_known_at": at, "reason": "WMT news article publication date (StreamingQA evidence_ts)",
                                                "declared_by": "process:factblock-bench-streamingqa/0.1", "captured_at": dt.datetime.now(dt.timezone.utc).isoformat()}
                                               for at, b in batches.items()]}}
    factblock.write_bundle({"manifest": manifest, "nodes": nodes, "edges": []}, out)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--questions", type=int, default=500)
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args()
    qa = rows()
    path = bundle(qa)
    b = factblock.Bundle(path)
    print(f"corpus: {len(b.nodes)} blocks, {len(b.backfills)} batches (one per article date)")
    sample = random.Random(a.seed).sample(qa, a.questions)
    t0 = time.time()
    qs, hidden = [], []
    for r in sample:
        asked = iso(r["question_ts"])
        ignorant = recall(b, r["question"], FAR, limit=a.k)
        honest = recall(b, r["question"], asked, limit=a.k)
        qs.append({"id": r["qa_id"], "asked_at": asked, "recent_or_past": r["recent_or_past"], "evidence": [i["id"] for i in ignorant["items"]]})
        hidden.append(honest["certificate"].get("masked", {}).get("node", 0))
    qfile = DATA / f"questions-k{a.k}-seed{a.seed}.jsonl"
    qfile.write_text("".join(json.dumps(q) + "\n" for q in qs))
    r = factblock.leak(b, qfile)
    by = {}
    for q, src in zip(r["per_question"], qs):
        by.setdefault(src["recent_or_past"], [0, 0])
        by[src["recent_or_past"]][0] += 1
        by[src["recent_or_past"]][1] += bool(q["leaked"])
    slots = sum(len(q["evidence"]) for q in qs)
    (pathlib.Path(__file__).parent / "results.json").write_text(json.dumps({   # what README and `factblock demo leak` read
        "corpus": "StreamingQA (DeepMind, CC-BY 4.0)", "k": a.k, "seed": a.seed, "questions": r["questions"],
        "leaked_questions": r["leaked_questions"], "leaked_blocks": r["leaked_blocks"], "picks": slots,
        "as_of_leaked_questions": 0, "as_of_hidden_per_question": round(sum(hidden) / len(hidden))}, indent=1) + "\n")
    print(f"{a.questions} questions, top-{a.k}, {time.time() - t0:.0f}s")
    print()
    print("| read | questions that rest on a block learned after they were asked | leaked blocks among all picks |")
    print("|---|---|---|")
    print(f"| time-ignorant (as_of = {FAR}) | **{r['leaked_questions']}/{r['questions']} = {r['leak_rate']:.1%}** | {r['leaked_blocks']}/{slots} = {r['leaked_blocks'] / slots:.1%} |")
    print(f"| as-of the question date | 0/{r['questions']} = 0% by construction | 0; it hid {sum(hidden) / len(hidden):,.0f} blocks per question on average to do so |")
    print()
    print("| questions | n | time-ignorant leak rate |")
    print("|---|---|---|")
    for k_, (n, l) in sorted(by.items()):
        print(f"| {k_} | {n} | {l / n:.1%} |")
    print(f"\nquestion set written to {qfile}; `factblock leak {path} {qfile}` reproduces the first row.")


if __name__ == "__main__":
    main()
