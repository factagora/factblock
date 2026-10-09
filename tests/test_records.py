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

    # re-importing the same rows would duplicate them: refused, folder untouched
    before = (d / "brain" / "nodes.jsonl").read_text()
    p = subprocess.run([sys.executable, "-m", "factblock", "import", str(d / "kb.csv"), "-o", str(d / "brain"), "--backfill"], capture_output=True, text=True)
    assert p.returncode != 0 and "I3.node_unique" in p.stderr and "Traceback" not in p.stderr, p.stderr
    assert (d / "brain" / "nodes.jsonl").read_text() == before

    # write_bundle: plain rows, no manifest, no attestation; input left alone
    rows = {"nodes": [{"id": "a", "statement": "x", "kind": "claim", "asserted_at": "2025-01-01", "known_at": "2025-01-02"}]}
    snap = copy.deepcopy(rows)
    factblock.write_bundle(rows, d / "plain")
    assert rows == snap and all(c.ok for c in factblock.validate(d / "plain"))
    for bad, why in (({"nodes": [{"id": "a", "statement": "x", "asserted_at": "2025-01-01"}]}, "has no known_at"),
                     ({"nodes": [{"id": "a", "statement": "x", "asserted_at": "2025-01-01", "known_at": "2025-01-02",
                                  "attestation": {"batch": "nope"}}]}, "I2.batch_exists")):
        try:
            factblock.write_bundle(bad, d / "bad"); raise AssertionError(why)
        except ValueError as e:
            assert why in str(e), e
        assert not (d / "bad").exists()
    try:
        factblock.from_records([{"text": "no date"}]); raise AssertionError
    except ValueError as e:
        assert "needs asserted_at" in str(e)
print("PASS records: CSV import (replacement before it takes effect, late correction, verdict) reads right as of each date; batches declared; duplicate import and invalid rows refused before writing; input not mutated")
