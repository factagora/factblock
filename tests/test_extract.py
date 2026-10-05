"""extract with the fake provider: a bundle that validates, is masked before known_at, carries the
speaker's causal chain as typed edges and MENTIONS to entities, and grows by appending a second
batch that reuses the entity. Run: uv run python tests/test_extract.py"""
import json
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import factblock  # noqa: E402

TEXT = "The Fed will keep raising rates this year. That means bond yields keep climbing, so I would stay out of long bonds."

with tempfile.TemporaryDirectory() as d:
    r = factblock.extract(TEXT, "2024-03-20T12:00:00Z", speaker="Jim Cramer", source="youtube", provider="fake",
                          known_at="2024-03-21T00:00:00Z")
    factblock.write_bundle(r, d)
    checks = factblock.validate(d)
    assert all(c.ok for c in checks), [c for c in checks if not c.ok]
    kinds = sorted(n["kind"] for n in r["nodes"])
    assert kinds.count("prediction") == 2 and kinds.count("claim") == 0, kinds           # two sentences, both with a forward-looking cue
    assert kinds.count("entity") >= 1, kinds                                               # "Fed" is capitalized mid-sentence
    assert all(n["asserted_at"] == "2024-03-20T12:00:00Z" for n in r["nodes"])
    assert all(n["known_at"] == "2024-03-21T00:00:00Z" and n["attestation"]["batch"] == r["summary"]["batch"] for n in r["nodes"])
    assert [n["author"] for n in r["nodes"] if n["kind"] != "entity"] == ["human:jim-cramer"] * 2
    types = sorted(e["edge_type"] for e in r["edges"])
    assert types.count("CAUSES") == 1 and types.count("MENTIONS") >= 1, types

    before = factblock.scan(d, as_of="2024-03-20T23:00:00Z")
    after = factblock.scan(d, as_of="2024-04-01")
    assert before.nodes.num_rows == 0 and before.certificate["masked"]["node"] == len(r["nodes"]), before.certificate
    assert after.nodes.num_rows == len(r["nodes"]) and after.certificate["backfill"]["rows"] == len(r["nodes"]) + len(r["edges"])

    # a second batch into the same folder: appended, still valid, the entity is reused not duplicated
    r2 = factblock.extract("The Fed paused in June. Markets rallied.", "2024-06-15", speaker="Jim Cramer", provider="fake",
                           known_at="2024-06-16T00:00:00Z", existing=factblock.Bundle(d))
    factblock.write_bundle(r2, d, append=True)
    assert all(c.ok for c in factblock.validate(d)), [c for c in factblock.validate(d) if not c.ok]
    b = factblock.Bundle(d)
    assert len(b.backfills) == 2
    assert [n["statement"] for n in b.nodes if n["kind"] == "entity"].count("Fed") == 1, "entity reused"
    assert factblock.scan(d, as_of="2024-07-01").nodes.num_rows == len(b.nodes)

    # the CLI end to end, stdin in, summary line out
    out = subprocess.run([sys.executable, "-m", "factblock", "extract", "-", "--observed-at", "2024-09-01", "--provider", "fake",
                          "-o", d, "--speaker", "Jim Cramer", "--backfill"], input="Rates will fall by year end.", capture_output=True, text=True, check=True)
    assert "+1 blocks" in out.stdout and "batch extract-" in out.stdout, out.stdout
    b = factblock.Bundle(d)
    assert len(b.backfills) == 3
    assert any(x["declared_known_at"].isoformat().startswith("2024-09-01") for x in b.backfills.values()), "--backfill: known when said"

print("PASS extract: fake provider -> valid bundle, masked before known_at, causal edges, entity reuse on append, CLI")
