"""The one check that fails if meaning in recall breaks: with words alone "price" misses the block that says
"costs" (first-use test U1); with an embed function it finds it, ranked by the fused word and meaning ranks, still
read as of as_of. Statement vectors are cached beside the bundle (the second recall embeds only the question),
and vectors the bundle declares for the same model are used as they are.
Run: uv run python tests/test_embed.py"""
import json
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import factblock  # noqa: E402

CONCEPTS = [{"price", "prices", "cost", "costs", "pricing", "fee"}, {"refund", "refunds", "money", "back"}, {"seat", "seats", "user", "users"}]
calls = []


def fake(texts):
    """A toy embedding: one axis per concept, so synonyms land together."""
    calls.append(len(texts))
    out = []
    for t in texts:
        words = set(t.lower().replace("?", " ").replace(".", " ").split())
        out.append([float(len(words & c)) for c in CONCEPTS] + [0.01])
    return out


fake.model = "fake:concepts"

with tempfile.TemporaryDirectory() as tmp:
    brain = pathlib.Path(tmp) / "brain"
    shutil.copytree(ROOT / "examples" / "support-agent" / "brain", brain)
    ids = lambda r: [i["id"] for i in r["items"]]   # noqa: E731

    words = factblock.recall(brain, "price", "2026-01-20")
    assert not any(i.startswith("price-") for i in ids(words)), ids(words)

    calls.clear()
    meant = factblock.recall(brain, "price", "2026-01-20", embed=fake)
    assert ids(meant) == ["price-20"] and meant["items"][0]["similarity"] > 0.5, meant["items"][:2]   # nothing unrelated rides along
    assert "price-25" not in ids(meant)            # announced 2026-02-15: still not known on 2026-01-20
    first = sum(calls)
    assert first > 1 and list((brain / ".factblock-cache").glob("embeddings-fake_concepts.json"))

    calls.clear()
    factblock.recall(brain, "seat cost", "2026-01-20", embed=fake)
    assert calls == [1], calls                     # every statement came from the cache; only the question was embedded
    assert "price-25" in ids(factblock.recall(brain, "seat cost", "2026-03-10", embed=fake))

    # a bundle that carries vectors for the same model: used as they are
    m = json.loads((brain / "factblock.json").read_text())
    m.setdefault("declarations", {})["embedding"] = {"model": "fake:concepts", "dimensions": 4}
    (brain / "factblock.json").write_text(json.dumps(m))
    rows = [json.loads(l) for l in (brain / "nodes.jsonl").read_text().splitlines() if l.strip()]
    for r in rows:
        r["embedding"] = fake([r["statement"]])[0]
    (brain / "nodes.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    shutil.rmtree(brain / ".factblock-cache")
    calls.clear()
    assert ids(factblock.recall(brain, "price", "2026-01-20", embed=fake))[0] == "price-20" and calls == [1], calls
    assert all(c.ok for c in factblock.validate(brain)), [c for c in factblock.validate(brain) if not c.ok]

    # context and timeline take the same embed
    assert "costs $20" in factblock.context(brain, "price", "2026-01-20", embed=fake)
print("PASS embed: words miss price/costs, meaning finds it (fused rank, as_of still masks), vectors cached beside the bundle, a bundle's own vectors for the same model used, context and recall")
