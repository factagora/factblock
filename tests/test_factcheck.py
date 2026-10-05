"""The one check that fails if the fact-check adapter breaks: claims become nodes, reviews become
verdict rows under batches at their review dates, ratings normalise, re-import adds nothing, the
folder validates and masks by review date. Run: uv run python tests/test_factcheck.py"""
import json
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import factblock  # noqa: E402
from factblock.adapters.factcheck import bundle_from_factcheck  # noqa: E402

FIX = pathlib.Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "factcheck-sample.json"
claims = json.load(FIX.open())["claims"]
r = bundle_from_factcheck(claims)
assert r["summary"] == {"claims": 3, "verdicts": 4, "batches": 4}, r["summary"]     # the unreviewed claim is skipped
crime = next(n for n in r["nodes"] if n["statement"].startswith("Crime"))
assert crime["asserted_at"] == "2024-02-10T00:00:00+00:00" and crime["known_at"] == "2024-02-14T00:00:00+00:00" and crime["payload"]["speaker"] == "A. Candidate"
vs = sorted((v for v in r["resolutions"] if v["target_id"] == crime["id"]), key=lambda v: v["decided_at"])
assert [v["outcome"] for v in vs] == ["mostly_false", "false"] and vs[0]["value"] == "Mostly False" and vs[0]["resolver"] == "org:factchecks.example"
assert vs[0]["evidence"][0]["url"] == "https://factchecks.example/crime-doubled" and vs[0]["known_at"] == vs[0]["decided_at"]
nodate = next(n for n in r["nodes"] if n["statement"].startswith("A claim without"))
assert nodate["asserted_at"] == "2024-06-01T00:00:00+00:00"                         # no claimDate: the first review dates it
assert "outcome" not in next(v for v in r["resolutions"] if v["target_id"] == nodate["id"])   # "Four Pinocchios" is kept as value only

with tempfile.TemporaryDirectory() as d:
    out = pathlib.Path(d) / "fc"
    factblock.write_bundle(r, out)
    checks = factblock.validate(out)
    assert all(c.ok for c in checks), [c for c in checks if not c.ok]
    assert factblock.scan(out, "2024-02-20").nodes.num_rows == 1 and factblock.scan(out, "2024-02-20").resolutions.num_rows == 1
    assert factblock.scan(out, "2024-07-01").resolutions.num_rows == 4
    again = bundle_from_factcheck(claims, existing=factblock.Bundle(out))
    assert again["summary"]["claims"] == 0 and again["summary"]["verdicts"] == 0, again["summary"]
    cr = factblock.to_claimreview(out, "2024-07-01")["@graph"]
    assert {c["factblock:id"]: c["reviewRating"]["alternateName"] for c in cr}[crime["id"]] == "False"   # latest review wins
    p = subprocess.run([sys.executable, "-m", "factblock", "from-factcheck", "-o", str(pathlib.Path(d) / "cli"), "--from-json", str(FIX)], capture_output=True, text=True, check=True)
    assert "+3 claims, +4 verdicts, 4 batches" in p.stdout, p.stdout
print("PASS factcheck: 3 claims, 4 verdicts under review-date batches, ratings normalised, validate, as-of, idempotent re-import, ClaimReview round trip, CLI")
