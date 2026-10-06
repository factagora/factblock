"""The factblock command. `factblock --help` lists the subcommands in the order you meet them:
sample, extract, scan, recall, why, resolve, leak, validate, sync, then the projections and adapters.
Reads print for people; `--json` prints the same answer as JSON."""
import argparse
import json
import os
import pathlib
import shutil
import sys

from . import Bundle, TckgStore, extract, leak, recall, resolve, scan, sync, to_claimreview, to_okf, validate, why, write_bundle, write_parquet
from .adapters.factcheck import bundle_from_factcheck, search as factcheck_search

# the wheel carries samples/rates at factblock/samples/rates (pyproject force-include); a checkout has it at the repo root
SAMPLES = next((d for d in (pathlib.Path(__file__).parent / "samples", pathlib.Path(__file__).resolve().parents[1] / "samples") if (d / "rates").exists()), None)


def _day(v):
    return v.date().isoformat() if hasattr(v, "date") else str(v)[:10]


def _cert(c):
    m = c.get("masked", {}); b = c.get("backfill")
    parts = [f"as of {c['as_of'][:10]}"]
    if c.get("valid_at", "")[:10] != c["as_of"][:10]:
        parts.append(f"valid at {c['valid_at'][:10]}")
    parts.append("hidden: " + (", ".join(f"{n} {k}{'s' if n != 1 else ''}" for k, n in m.items()) if m else "nothing"))
    if c.get("not_in_force"):
        parts.append("not in force: " + ", ".join(f"{n} {k}{'s' if n != 1 else ''}" for k, n in c["not_in_force"].items()))
    if b:
        parts.append(f"backfilled: {b['rows']} rows in {b['batches']} batch{'es' if b['batches'] != 1 else ''}")
    return "  ".join(parts)


def _print_scan(r):
    print(_cert(r.certificate))
    nodes = r.nodes.to_pylist()
    for n in sorted(nodes, key=lambda n: (n["asserted_at"], n["id"])):
        tail = f"   [superseded by {n['superseded_by']}]" if n.get("superseded_by") else ""
        print(f"{n['id']:<12} {n['kind']:<11} {_day(n['asserted_at'])}  {n.get('statement') or ''}{tail}")
    if r.edges.num_rows:
        print("edges:")
        for e in sorted(r.edges.to_pylist(), key=lambda e: (e["asserted_at"], e["source_id"])):
            print(f"  {e['source_id']} --{e['edge_type']}--> {e['target_id']}   {_day(e['asserted_at'])}")
    if r.resolutions.num_rows:
        print("verdicts:")
        for v in sorted(r.resolutions.to_pylist(), key=lambda v: v["decided_at"]):
            print(f"  {v['target_id']:<12} {v.get('outcome') or v.get('value')}   decided {_day(v['decided_at'])}" + (f"   by {v['resolver']}" if v.get("resolver") else ""))


def _print_why(r):
    if not r["chain"]:
        print(f"{r['root']}: {r.get('reason', 'no chain')}   {_cert(r['certificate'])}")
        return
    for row in sorted(r["chain"], key=lambda x: (len(x["path"]), x["path"])):
        via = f" ({row['via']['edge_type']})" if row["via"] else ""
        print("    " * row["depth"] + f"{row['role']}{via}: {row['id']}  {_day(row['asserted_at'])}  {row['statement'] or ''}")
    print(_cert(r["certificate"]))


def _print_resolve(k, r):
    if r["status"] == "answered":
        print(f"{k}: {json.dumps(r['value'])}   policy {r.get('policy')}, {len(r['candidates'])} candidate{'s' if len(r['candidates']) != 1 else ''}")
    else:
        print(f"{k}: no answer, {r['reason']}" + (f" since {r['unresolved_since'][:10]}" if r.get("unresolved_since") else ""))
        for c in r.get("candidates", []):
            print(f"  {c['id']:<12} {json.dumps(c['value'])}   valid from {c['valid_from'][:10]}   known {c['known_at'][:10]}")
    print(_cert(r["certificate"]))


def main():
    p = argparse.ArgumentParser(prog="factblock", description="Agent memory for decisions: dated claims and their causal links, in a folder, read as of any instant.")
    sub = p.add_subparsers(dest="cmd", metavar="command")

    def cmd(name, help_, as_of=True, valid_at=True, json_=True):
        s = sub.add_parser(name, help=help_, description=help_)
        s.add_argument("bundle", help="the bundle directory")
        if as_of:
            s.add_argument("--as-of", required=True, help="the instant to read as of (date or ISO 8601); nothing learned later is shown")
        if valid_at:
            s.add_argument("--valid-at", help="the instant the content must hold at; default: as-of")
        if json_:
            s.add_argument("--json", action="store_true", help="print the answer as JSON")
        return s

    s = sub.add_parser("sample", help="copy the sample bundle (six dated claims, a reversal, three verdicts) into a folder", description="copy the sample bundle into a folder")
    s.add_argument("out", help="folder to create, e.g. brain/")
    e = sub.add_parser("extract", help="text in, dated blocks and their links appended to a bundle", description="text in, dated blocks and their links appended to a bundle")
    e.add_argument("source", help="a text file, or - for stdin")
    e.add_argument("--observed-at", required=True, help="when it was said or written (ISO 8601)")
    e.add_argument("-o", "--out", required=True, help="bundle directory; created or appended to")
    e.add_argument("--speaker", help="who said it, as written")
    e.add_argument("--source-name", dest="source_name", help="where it came from (a channel, a document)")
    e.add_argument("--provider", default="gemini", choices=["gemini", "openai", "fake"], help="gemini (GEMINI_API_KEY or Vertex), openai (OPENAI_API_KEY), or fake: no model, sentence split, for trying the format")
    e.add_argument("--model", help="model name for the provider")
    e.add_argument("--known-at", help="when you learned it; default now")
    e.add_argument("--backfill", action="store_true", help="known_at = observed_at: material from the past, known when it was said")
    e.add_argument("--namespace", default="local")
    cmd("scan", "what the folder knew as of an instant: blocks, edges, verdicts, and what was hidden")
    rc = cmd("recall", "the blocks about something as of an instant, ranked; the read an agent makes before it answers")
    rc.add_argument("query", help="words to look for in statements, quotes and speakers")
    rc.add_argument("--limit", type=int, default=10)
    rc.add_argument("--all-kinds", action="store_true", help="include entities and episodes, not only claims and predictions")
    w = cmd("why", "the chain behind one block as of an instant: causes, effects, successors, contradictions")
    w.add_argument("node_id", help="the block id (see scan)")
    w.add_argument("--depth", type=int, default=3, help="hops to walk; default 3")
    r = cmd("resolve", "one value for a declared fact, by its declared policy, or the reason there is none")
    r.add_argument("fact_key", help="the declared fact, e.g. belief:fed:direction")
    r.add_argument("--rules-as-of", help="apply the declaration in force at this instant instead of as-of")
    k = cmd("leak", "which answers in a dated question set rest on blocks learned after the question was asked", as_of=False, valid_at=False, json_=False)
    k.add_argument("questions", help="JSONL: {id?, asked_at, evidence: [block id, ...]} per line")
    cmd("validate", "the conformance checks of SPEC.md section 2; exit 1 if any fails", as_of=False, valid_at=False, json_=False)
    y = sub.add_parser("sync", help="folder <-> a hosted ledger, both ways, by identity; known_at travels as batches", description="folder <-> a hosted ledger (tckg), both ways")
    y.add_argument("bundle")
    y.add_argument("url", help="the ledger, e.g. https://tckg.factagora.com")
    y.add_argument("--space", help="whose memory this is on the ledger; rows that carry their own space keep it")
    y.add_argument("--token", help="API key of the tenant; default $TCKG_TOKEN")
    y.add_argument("--as-of", help="pull rows the ledger knew by this instant; default now")
    y.add_argument("--push-only", action="store_true")
    y.add_argument("--pull-only", action="store_true")
    cr = cmd("to-claimreview", "verdicts visible as of an instant, as schema.org ClaimReview JSON-LD", json_=False)
    cr.add_argument("--base-url", help="each review's url becomes <base-url>/<block id>")
    ok = cmd("to-okf", "the blocks visible as of an instant, as an OKF bundle (markdown + frontmatter)", json_=False)
    ok.add_argument("out", help="directory to write")
    c = sub.add_parser("to-parquet", help="the same bundle in the Parquet profile, for DuckDB, Spark, Databricks", description="JSONL bundle to the Parquet profile")
    c.add_argument("bundle"); c.add_argument("out")
    fc = sub.add_parser("from-factcheck", help="published fact-checks in (Google Fact Check Tools API shape), dated claims with dated verdicts out", description="fact-checks in, dated claims with dated verdicts out")
    fc.add_argument("-o", "--out", required=True, help="bundle directory; created or appended to")
    fc.add_argument("--query", help="search the live API; needs --api-key or $FACTCHECK_API_KEY")
    fc.add_argument("--language", help="BCP-47 filter for --query, e.g. en or ko")
    fc.add_argument("--pages", type=int, default=1, help="pages of 100 to fetch for --query")
    fc.add_argument("--api-key")
    fc.add_argument("--from-json", help="a saved claims:search response, or a JSON array of claims")
    fc.add_argument("--namespace", default="factcheck")
    a = p.parse_args()
    if not a.cmd:                       # bare `factblock`: show what it can do, not an error
        p.print_help()
        print("\nStart here: factblock sample brain/ && factblock scan brain/ --as-of 2024-05-01")
        return
    out_json = lambda d: print(json.dumps(d, indent=1, default=str))  # noqa: E731

    if a.cmd == "sample":
        if pathlib.Path(a.out).exists():
            p.error(f"{a.out} exists; pick a new folder")
        shutil.copytree(SAMPLES / "rates", a.out)
        print(f"{a.out}: the sample bundle. Try: factblock scan {a.out} --as-of 2024-05-01")
    elif a.cmd == "extract":
        text = sys.stdin.read() if a.source == "-" else open(a.source).read()
        existing = Bundle(a.out) if (pathlib.Path(a.out) / "factblock.json").exists() else None
        r = extract(text, a.observed_at, speaker=a.speaker, source=a.source_name, provider=a.provider, model=a.model,
                    known_at=a.known_at, backfill=a.backfill, namespace=a.namespace, existing=existing)
        write_bundle(r, a.out, append=True)
        s_ = r["summary"]
        print(f"{a.out}: +{s_['blocks']} blocks, +{s_['entities']} entities, +{s_['links']} links"
              + (f" ({s_['links_dropped']} dropped)" if s_['links_dropped'] else "") + f", batch {s_['batch']}")
    elif a.cmd == "scan":
        r = scan(a.bundle, a.as_of, a.valid_at)
        if a.json:
            out_json({"certificate": r.certificate,
                      "nodes": r.nodes.select([c for c in ("id", "kind", "statement", "asserted_at", "superseded_by") if c in r.nodes.column_names]).to_pylist(),
                      "edges": r.edges.select(["source_id", "target_id", "edge_type", "asserted_at"]).to_pylist() if r.edges.num_rows else [],
                      "resolutions": r.resolutions.to_pylist()})
        else:
            _print_scan(r)
    elif a.cmd == "recall":
        r = recall(a.bundle, a.query, a.as_of, a.valid_at, a.limit, kinds=() if a.all_kinds else ("claim", "prediction"))
        if a.json:
            out_json(r)
        else:
            for i in r["items"]:
                print(f"{i['id']:<12} {i['kind']:<11} {_day(i['asserted_at'])}  {i['statement']}" + (f"   ({i['speaker']})" if i.get("speaker") else ""))
            print(f"{len(r['items'])} of {r['matched']} matching   {_cert(r['certificate'])}")
    elif a.cmd == "why":
        r = why(a.bundle, a.node_id, a.as_of, a.valid_at, a.depth)
        out_json(r) if a.json else _print_why(r)
    elif a.cmd == "resolve":
        r = resolve(a.bundle, a.fact_key, a.as_of, a.valid_at, a.rules_as_of)
        out_json(r) if a.json else _print_resolve(a.fact_key, r)
    elif a.cmd == "leak":
        r = leak(a.bundle, a.questions)
        for q in r["per_question"]:
            if q["leaked"] or q["missing"]:
                print(f"{q['id']}: asked {q['asked_at'][:10]}, " + ", ".join(f"{l['id']} known {l['known_at'][:10]} ({l['reason']})" for l in q["leaked"])
                      + (f", missing {q['missing']}" if q["missing"] else ""))
        print(f"{r['leaked_questions']}/{r['questions']} questions leak ({r['leak_rate']:.0%}), {r['leaked_blocks']} blocks learned after the question"
              + (f", {r['missing_blocks']} evidence ids not in the bundle" if r["missing_blocks"] else ""))
        sys.exit(1 if r["leaked_questions"] else 0)
    elif a.cmd == "validate":
        checks = validate(a.bundle)
        for c in checks:
            print(f"{'ok  ' if c.ok else 'FAIL'} {c.check_id:<20} {c.detail}")
        sys.exit(0 if all(c.ok for c in checks) else 1)
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
    elif a.cmd == "to-claimreview":
        out_json(to_claimreview(a.bundle, a.as_of, a.base_url, a.valid_at))
    elif a.cmd == "to-okf":
        out = to_okf(a.bundle, a.as_of, a.out, a.valid_at)
        print(f"wrote {out}: {len(list(out.glob('*.md')))} documents")
    elif a.cmd == "to-parquet":
        out = write_parquet(a.bundle, a.out)
        print(f"wrote {out}: {sorted(x.name for x in out.iterdir())}")
    elif a.cmd == "from-factcheck":
        if a.from_json:
            d = json.load(open(a.from_json))
            claims = d.get("claims", []) if isinstance(d, dict) else d
        elif a.query:
            key = a.api_key or os.environ.get("FACTCHECK_API_KEY") or p.error("--api-key or $FACTCHECK_API_KEY is required with --query")
            claims = factcheck_search(a.query, key, a.language, a.pages)
        else:
            p.error("one of --query or --from-json is required")
        existing = Bundle(a.out) if (pathlib.Path(a.out) / "factblock.json").exists() else None
        r = bundle_from_factcheck(claims, existing, a.namespace)
        write_bundle(r, a.out, append=True)
        s_ = r["summary"]
        print(f"{a.out}: +{s_['claims']} claims, +{s_['verdicts']} verdicts, {s_['batches']} batches")


def run():
    try:
        main()
    except BrokenPipeError:        # `factblock scan ... | head`
        sys.stderr.close()


if __name__ == "__main__":
    run()
