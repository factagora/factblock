"""python -m factblock validate <bundle> | scan <bundle> --as-of <instant> [--valid-at <instant>]"""
import argparse
import json
import sys

from . import scan, validate

p = argparse.ArgumentParser(prog="factblock")
sub = p.add_subparsers(dest="cmd", required=True)
sub.add_parser("validate").add_argument("bundle")
s = sub.add_parser("scan")
s.add_argument("bundle")
s.add_argument("--as-of", required=True)
s.add_argument("--valid-at")
a = p.parse_args()

if a.cmd == "validate":
    checks = validate(a.bundle)
    for c in checks:
        print(f"{'ok  ' if c.ok else 'FAIL'} {c.check_id:<20} {c.detail}")
    sys.exit(0 if all(c.ok for c in checks) else 1)
else:
    r = scan(a.bundle, a.as_of, a.valid_at)
    print(json.dumps({"certificate": r.certificate,
                      "nodes": r.nodes.select([c for c in ("id", "kind", "statement", "superseded_by") if c in r.nodes.column_names]).to_pylist(),
                      "edges": r.edges.select(["source_id", "target_id", "edge_type"]).to_pylist() if r.edges.num_rows else []},
                     indent=1, default=str))
