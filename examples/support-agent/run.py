"""Five support questions, two memories. Prints what each memory puts into the agent's prompt and
scores it: a stale statement in the prompt with nothing marking it stale is a fail.

    python examples/support-agent/run.py            # from the repo root
    python examples/support-agent/run.py --json

"Date filter" is what most memories do with time: keep statements said on or before the question,
rank by match then recency. FactBlock's context() reads as of the question instead: only what was
known then, only what was in force then, with replacements and verdicts attached."""
import json
import sys
from pathlib import Path

import factblock
from factblock.bundle import Bundle, parse_instant
from factblock.recall import _hits, _terms

HERE = Path(__file__).resolve().parent
BRAIN = HERE / "brain"


def date_filter(bundle, query, asked_at, limit=10):
    """The baseline: asserted_at <= asked_at, keyword hits, newest first. No known_at, no validity,
    no SUPERSEDES, no verdicts, because a timestamp column does not carry them."""
    t, terms = parse_instant(asked_at), _terms(query)
    rows = [n for n in bundle.nodes if n["asserted_at"] <= t and n["kind"] in ("claim", "prediction")]
    hits = [(_hits(terms, n), n) for n in rows]
    hits = sorted([(s, n) for s, n in hits if s], key=lambda x: (-x[0], -x[1]["asserted_at"].timestamp()))[:limit]
    items = [{"id": n["id"], "statement": n["statement"], "asserted_at": n["asserted_at"]} for _, n in hits]
    text = "\n".join(f"- {i['asserted_at'].date()}: {i['statement']}" for i in items)
    return items, text


def score(items, q):
    """Pass when every current statement is in the prompt as current, no stale one is, and the verdicts asked for are there."""
    current = {i["id"] for i in items if not i.get("superseded_by")}
    verdicts = {i["id"]: (i.get("verdict") or {}).get("outcome") for i in items}
    why = [f"missing {x}" for x in q["current"] if x not in current]
    why += [f"stale {x} shown as current" for x in q["stale"] if x in current]
    why += [f"no verdict for {k}" for k, v in q.get("verdict", {}).items() if verdicts.get(k) != v]
    return not why, why


def evaluate():
    b = Bundle(BRAIN)
    out = []
    for q in (json.loads(l) for l in (HERE / "questions.jsonl").open() if l.strip()):
        base_items, base_text = date_filter(b, q["query"], q["asked_at"])
        fb_items = factblock.recall(b, q["query"], q["asked_at"])["items"]
        fb_text = factblock.context(b, q["query"], q["asked_at"])
        out.append({**q, "date_filter": {"context": base_text, "pass": score(base_items, q)[0], "why": score(base_items, q)[1]},
                    "factblock": {"context": fb_text, "pass": score(fb_items, q)[0], "why": score(fb_items, q)[1]}})
    return out


def main():
    res = evaluate()
    if "--json" in sys.argv:
        print(json.dumps(res, indent=1, default=str))
        return
    for r in res:
        print(f"\n{r['id']}  {r['question']}   (asked {r['asked_at'][:10]}; {r['kind']})")
        for name in ("date_filter", "factblock"):
            x = r[name]
            print(f"  {name.replace('_', ' '):<12} {'PASS' if x['pass'] else 'FAIL: ' + '; '.join(x['why'])}")
            print("\n".join("      " + line for line in x["context"].splitlines()))
    n = len(res)
    print(f"\ndate filter {sum(r['date_filter']['pass'] for r in res)}/{n}, factblock {sum(r['factblock']['pass'] for r in res)}/{n}")


if __name__ == "__main__":
    main()
