"""python -m factblock validate <bundle> | scan <bundle> --as-of T [--valid-at T]
   | resolve <bundle> <fact_key> --as-of T [--valid-at T] [--rules-as-of T] | to-parquet <bundle> <out>"""
import argparse
import json
import sys

from . import resolve, scan, validate, write_parquet


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
    c = sub.add_parser("to-parquet")
    c.add_argument("bundle")
    c.add_argument("out")
    a = p.parse_args()

    if a.cmd == "validate":
        checks = validate(a.bundle)
        for c in checks:
            print(f"{'ok  ' if c.ok else 'FAIL'} {c.check_id:<20} {c.detail}")
        sys.exit(0 if all(c.ok for c in checks) else 1)
    elif a.cmd == "to-parquet":
        out = write_parquet(a.bundle, a.out)
        print(f"wrote {out}: {sorted(x.name for x in out.iterdir())}")
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
