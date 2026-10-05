"""python -m factblock extract <file|-> --observed-at T -o <bundle> [--speaker S] [--source S] [--provider gemini|openai|fake] [--model M] [--known-at T | --backfill]
   | validate <bundle> | scan <bundle> --as-of T [--valid-at T]
   | resolve <bundle> <fact_key> --as-of T [--valid-at T] [--rules-as-of T]
   | why <bundle> <node_id> --as-of T [--valid-at T] [--depth N] | leak <bundle> <questions.jsonl>
   | sync <bundle> <url> --space S [--token T] [--as-of T] [--push-only | --pull-only]
   | to-claimreview <bundle> --as-of T [--base-url U] | to-parquet <bundle> <out>"""
import argparse
import json
import os
import pathlib
import sys

from . import Bundle, TckgStore, extract, leak, resolve, scan, sync, to_claimreview, validate, why, write_bundle, write_parquet


def main():

    p = argparse.ArgumentParser(prog="factblock")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate").add_argument("bundle")
    s = sub.add_parser("scan")
    s.add_argument("bundle")
    s.add_argument("--as-of", required=True)
    s.add_argument("--valid-at")
    r = sub.add_parser("resolve")
    r.add_argument("bundle")
    r.add_argument("fact_key")
    r.add_argument("--as-of", required=True)
    r.add_argument("--valid-at")
    r.add_argument("--rules-as-of")
    w = sub.add_parser("why", help="the chain behind one block, as of an instant")
    w.add_argument("bundle")
    w.add_argument("node_id")
    w.add_argument("--as-of", required=True)
    w.add_argument("--valid-at")
    w.add_argument("--depth", type=int, default=3)
    k = sub.add_parser("leak", help="which answers in a question set rest on blocks learned after the question was asked")
    k.add_argument("bundle")
    k.add_argument("questions", help="JSONL: {id?, asked_at, evidence: [block id, ...]} per line")
    y = sub.add_parser("sync", help="folder <-> a tckg ledger, both ways, by identity; known_at travels as batches")
    y.add_argument("bundle")
    y.add_argument("url", help="the ledger, e.g. https://tckg.factagora.com")
    y.add_argument("--space", help="whose memory this is on the ledger; rows that carry their own space keep it")
    y.add_argument("--token", help="API key of the tenant; default $TCKG_TOKEN")
    y.add_argument("--as-of", help="pull rows the ledger knew by this instant; default now")
    y.add_argument("--push-only", action="store_true")
    y.add_argument("--pull-only", action="store_true")
    e = sub.add_parser("extract", help="text in, a batch of blocks appended to a bundle")
    e.add_argument("source", help="a text file, or - for stdin")
    e.add_argument("--observed-at", required=True, help="when it was said or written (ISO 8601)")
    e.add_argument("-o", "--out", required=True, help="bundle directory; created or appended to")
    e.add_argument("--speaker")
    e.add_argument("--source-name", dest="source_name", help="where it came from (a channel, a document)")
    e.add_argument("--provider", default="gemini", choices=["gemini", "openai", "fake"])
    e.add_argument("--model")
    e.add_argument("--known-at", help="when you learned it; default now")
    e.add_argument("--backfill", action="store_true", help="known_at = observed_at: material from the past, known when it was said")
    e.add_argument("--namespace", default="local")
    cr = sub.add_parser("to-claimreview", help="verdicts visible as of an instant, as schema.org ClaimReview JSON-LD")
    cr.add_argument("bundle")
    cr.add_argument("--as-of", required=True)
    cr.add_argument("--valid-at")
    cr.add_argument("--base-url", help="each review's url becomes <base-url>/<block id>")
    c = sub.add_parser("to-parquet")
    c.add_argument("bundle")
    c.add_argument("out")
    a = p.parse_args()

    if a.cmd == "extract":
        text = sys.stdin.read() if a.source == "-" else open(a.source).read()
        existing = Bundle(a.out) if (pathlib.Path(a.out) / "factblock.json").exists() else None
        r = extract(text, a.observed_at, speaker=a.speaker, source=a.source_name, provider=a.provider, model=a.model,
                    known_at=a.known_at, backfill=a.backfill, namespace=a.namespace, existing=existing)
        write_bundle(r, a.out, append=True)
        s_ = r["summary"]
        print(f"{a.out}: +{s_['blocks']} blocks, +{s_['entities']} entities, +{s_['links']} links"
              + (f" ({s_['links_dropped']} dropped)" if s_['links_dropped'] else "") + f", batch {s_['batch']}")
    elif a.cmd == "validate":
        checks = validate(a.bundle)
        for c in checks:
            print(f"{'ok  ' if c.ok else 'FAIL'} {c.check_id:<20} {c.detail}")
        sys.exit(0 if all(c.ok for c in checks) else 1)
    elif a.cmd == "to-claimreview":
        print(json.dumps(to_claimreview(a.bundle, a.as_of, a.base_url, a.valid_at), indent=1, default=str))
    elif a.cmd == "to-parquet":
        out = write_parquet(a.bundle, a.out)
        print(f"wrote {out}: {sorted(x.name for x in out.iterdir())}")
    elif a.cmd == "sync":
        token = a.token or os.environ.get("TCKG_TOKEN") or p.error("--token or $TCKG_TOKEN is required")
        r = sync(a.bundle, TckgStore(a.url, token, a.space), a.as_of, push=not a.pull_only, pull=not a.push_only)
        pu, pl = r["pushed"], r["pulled"]
        parts = []
        if pu is not None:
            parts.append(f"pushed {pu['accepted']} rows in {pu['batches']} batches" + (f", {len(pu['skipped'])} already there" if pu["skipped"] else "")
                         + (f", {len(pu['refused'])} refused" if pu["refused"] else "") + (f", {pu['resolutions_not_pushed']} resolutions kept local" if pu["resolutions_not_pushed"] else ""))
        if pl is not None:
            parts.append(f"pulled {pl['nodes']} nodes, {pl['edges']} edges, {pl['resolutions']} resolutions")
        print(f"{a.bundle} <-> {a.url}: " + "; ".join(parts) + f" (as of {r['as_of'][:19]})")
        for x in (pu or {}).get("refused", []):
            print(f"  refused {x}")
        sys.exit(1 if pu and pu["refused"] else 0)
    elif a.cmd == "leak":
        r = leak(a.bundle, a.questions)
        for q in r["per_question"]:
            if q["leaked"] or q["missing"]:
                print(f"{q['id']}: asked {q['asked_at'][:10]}, " + ", ".join(f"{l['id']} known {l['known_at'][:10]} ({l['reason']})" for l in q["leaked"])
                      + (f", missing {q['missing']}" if q["missing"] else ""))
        print(f"{r['leaked_questions']}/{r['questions']} questions leak ({r['leak_rate']:.0%}), {r['leaked_blocks']} blocks learned after the question"
              + (f", {r['missing_blocks']} evidence ids not in the bundle" if r["missing_blocks"] else ""))
        sys.exit(1 if r["leaked_questions"] else 0)
    elif a.cmd == "why":
        print(json.dumps(why(a.bundle, a.node_id, a.as_of, a.valid_at, a.depth), indent=1, default=str))
    elif a.cmd == "resolve":
        print(json.dumps(resolve(a.bundle, a.fact_key, a.as_of, a.valid_at, a.rules_as_of), indent=1, default=str))
    else:
        r = scan(a.bundle, a.as_of, a.valid_at)
        print(json.dumps({"certificate": r.certificate,
                          "nodes": r.nodes.select([c for c in ("id", "kind", "statement", "superseded_by") if c in r.nodes.column_names]).to_pylist(),
                          "edges": r.edges.select(["source_id", "target_id", "edge_type"]).to_pylist() if r.edges.num_rows else []},
                         indent=1, default=str))


if __name__ == "__main__":
    main()
