"""The one check that fails if the structured write path breaks: CSV rows in (statements, a replacement
announced before it takes effect, a correction learned late, verdicts), a valid bundle out whose
as-of reads use exactly the dates in the columns; write_bundle declares batches itself, leaves its
input alone, and refuses to write an invalid bundle. Run: uv run python tests/test_records.py"""
import copy
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import factblock  # noqa: E402

CSV = """id,said_at,effective_from,known_at,text,replaces,speaker,target,outcome,decided_at
p1,2026-01-10,,,The Team plan costs $30 per user per month.,,,,,
p2,2026-02-20,2026-03-15,,The Team plan costs $36 per user per month.,p1,,,,
s1,2026-01-10,,,The Team plan includes 50 GB of storage.,,,,,
s2,2026-04-02,,2026-04-18,The Team plan includes 100 GB of storage.,s1,,,,
k1,2026-02-01,,,We will ship SSO to Initech by 2026-03-31.,,Sam,,,
,,,,,,,k1,did_not,2026-04-02
"""

with tempfile.TemporaryDirectory() as d:
    d = pathlib.Path(d)
    (d / "kb.csv").write_text(CSV)
    p = subprocess.run([sys.executable, "-m", "factblock", "import", str(d / "kb.csv"), "-o", str(d / "brain"), "--backfill"], capture_output=True, text=True)
    assert p.returncode == 0 and "+5 blocks, +2 replaced, +1 verdicts" in p.stdout, p.stdout + p.stderr
    assert all(c.ok for c in factblock.validate(d / "brain"))
    b = factblock.Bundle(d / "brain")
    assert {x["batch"] for x in b.backfills.values()} == {"known-20260110T000000Z", "known-20260220T000000Z", "known-20260418T000000Z",
                                                         "known-20260201T000000Z", "known-20260402T000000Z"}
    assert next(n for n in b.nodes if n["id"] == "k1")["payload"] == {"speaker": "Sam"}

    def standing(query, as_of):   # what recall offers as current: matched and not replaced
        return [i["id"] for i in factblock.recall(d / "brain", query, as_of)["items"] if not i.get("superseded_by")]
    assert standing("costs", "2026-03-01") == ["p1"]    # $36 announced, not in force yet
    assert standing("costs", "2026-03-20") == ["p2"]    # $30 replaced on 03-15, still listed and marked
    assert standing("storage", "2026-04-10") == ["s1"]  # 100 GB said 04-02, learned 04-18
    assert standing("storage", "2026-04-20") == ["s2"]
    sso = factblock.recall(d / "brain", "SSO", "2026-04-05")["items"][0]
    assert sso["verdict"]["outcome"] == "did_not", sso

    # the replaced line gives the day the replacement took effect, and the announcement when it differs
    ctx = factblock.context(d / "brain", "costs", "2026-03-01")   # $36 announced 02-20, in force 03-15
    assert "  changes 2026-03-15 to: The Team plan costs $36 per user per month. (announced 2026-02-20)" in ctx, ctx
    assert factblock.recall(d / "brain", "costs", "2026-02-10")["items"][0].get("upcoming") is None   # not announced yet
    factblock.write_bundle({"nodes": [{"id": "a1", "kind": "claim", "statement": "The Team plan adds audit logs.", "asserted_at": "2026-02-25",
                                       "valid_from": "2026-04-01", "known_at": "2026-02-25"}]}, d / "brain", append=True)
    assert "- 2026-02-25: The Team plan adds audit logs. (takes effect 2026-04-01)" in factblock.context(d / "brain", "audit", "2026-03-01")
    ctx = factblock.context(d / "brain", "costs", "2026-03-20")
    assert "replaced 2026-03-15 by: The Team plan costs $36 per user per month. (announced 2026-02-20)" in ctx, ctx
    # a kind of your own is a statement too: recall and context show it; things are left out and counted
    factblock.write_bundle(factblock.from_records([{"id": "c1", "kind": "commitment", "text": "Globex gets audit export by April",
                                                    "said_at": "2026-02-01"}, {"id": "e1", "kind": "entity", "text": "Globex",
                                                    "said_at": "2026-02-01"}], backfill=True), d / "brain", append=True)
    r = factblock.recall(d / "brain", "Globex", "2026-03-01")
    assert [i["id"] for i in r["items"]] == ["c1"] and r["excluded"] == {"entity": 1}, r
    assert "Globex gets audit export" in factblock.context(d / "brain", "Globex", "2026-03-01")
    assert factblock.recall(d / "brain", "Globex", "2026-03-01", kinds=("claim",))["excluded"] == {"commitment": 1, "entity": 1}
    assert factblock.context(d / "brain", "zebra", "2026-03-01").startswith("(nothing about 'zebra' known as of 2026-03-01)")
    # filters: an empty query lists everything newest first; verdict narrows to an outcome, open or resolved;
    # imported columns (payload text) are searched
    assert [i["id"] for i in factblock.recall(d / "brain", "", "2026-04-05", verdict="did_not")["items"]] == ["k1"]
    assert "k1" not in [i["id"] for i in factblock.recall(d / "brain", "", "2026-04-05", verdict="open", limit=50)["items"]]
    assert [i["id"] for i in factblock.recall(d / "brain", "", "2026-03-30", verdict="resolved")["items"]] == []   # verdict learned 04-02
    assert factblock.recall(d / "brain", "", "2026-03-01", limit=50)["matched"] == 4   # p1 s1 k1 c1; p2 announced, not in force yet
    factblock.write_bundle(factblock.from_records([{"id": "c2", "kind": "commitment", "text": "SAML SSO by March", "customer": "Umbrella",
                                                    "said_at": "2026-02-02"}], backfill=True), d / "brain", append=True)
    assert [i["id"] for i in factblock.recall(d / "brain", "Umbrella", "2026-03-01")["items"]] == ["c2"]

    # re-importing is a no-op (rows the folder has are skipped by identity); a grown CSV adds only the new row;
    # the same id with a different statement is an edit: refused, folder untouched
    before = (d / "brain" / "nodes.jsonl").read_text()
    p = subprocess.run([sys.executable, "-m", "factblock", "import", str(d / "kb.csv"), "-o", str(d / "brain"), "--backfill"], capture_output=True, text=True)
    assert p.returncode == 0 and "+0 blocks, +0 replaced, +0 verdicts, 8 already there" in p.stdout, p.stdout + p.stderr
    assert (d / "brain" / "nodes.jsonl").read_text() == before
    (d / "kb.csv").write_text(CSV + "r1b,2026-05-01,,,Annual plans can be refunded within 14 days.,r1,,,,\n")
    p = subprocess.run([sys.executable, "-m", "factblock", "import", str(d / "kb.csv"), "-o", str(d / "brain"), "--backfill"], capture_output=True, text=True)
    assert "+1 blocks, +1 replaced, +0 verdicts, 8 already there" in p.stdout, p.stdout + p.stderr
    before = (d / "brain" / "nodes.jsonl").read_text()
    (d / "kb.csv").write_text(CSV.replace("$30 per user", "$29 per user"))
    p = subprocess.run([sys.executable, "-m", "factblock", "import", str(d / "kb.csv"), "-o", str(d / "brain"), "--backfill"], capture_output=True, text=True)
    assert p.returncode != 0 and "p1 is already in the bundle with different content" in p.stderr and "Traceback" not in p.stderr, p.stderr
    assert (d / "brain" / "nodes.jsonl").read_text() == before

    # write_bundle: plain rows, no manifest, no attestation; input left alone
    rows = {"nodes": [{"id": "a", "statement": "x", "kind": "claim", "asserted_at": "2025-01-01", "known_at": "2025-01-02"}]}
    snap = copy.deepcopy(rows)
    factblock.write_bundle(rows, d / "plain")
    assert rows == snap and all(c.ok for c in factblock.validate(d / "plain"))
    for bad, why in (({"nodes": [{"id": "a", "statement": "x", "asserted_at": "2025-01-01"}]}, "has no known_at"),
                     ({"nodes": [{"id": "a", "statement": "x", "asserted_at": "2025-01-01", "known_at": "2025-01-02",
                                  "attestation": {"batch": "nope"}}]}, "I2.batch_exists"),
                     ({**rows, "resolutions": [{"target_id": "zz", "value": "kept", "decided_at": "2025-02-01", "known_at": "2025-02-01"}]}, "I6.target_exists"),
                     ({**rows, "resolutions": [{"target_id": "a", "value": "kept", "decided_at": "2024-12-01", "known_at": "2025-02-01"}]}, "I6.after_statement")):
        try:
            factblock.write_bundle(bad, d / "bad"); raise AssertionError(why)
        except ValueError as e:
            assert why in str(e), e
        assert not (d / "bad").exists()
    try:
        factblock.from_records([{"text": "no date"}]); raise AssertionError
    except ValueError as e:
        assert "needs asserted_at" in str(e)
s = factblock.scan(pathlib.Path(__file__).resolve().parents[1] / "samples" / "rates", "2025-01-01")
assert {r["target_id"]: r["value"] for r in s.to_dicts("resolutions")}["c1"] in ("true", "false") and isinstance(s.to_dicts()[0].get("payload", {}), dict)
assert factblock.__version__ and factblock.__version__[0].isdigit()
print("PASS records: CSV import (replacement before it takes effect, late correction, verdict) reads right as of each date; replaced date is the effective one; announced changes shown before they take effect; any statement kind recalled, things counted as excluded, empty context says so; batches declared; re-import a no-op, a grown CSV adds only new rows, an edited row and invalid rows refused before writing; input not mutated; scan.to_dicts parses JSON columns; __version__")
