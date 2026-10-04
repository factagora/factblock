"""The adapter is the format's second writer. Duck-typed Graphiti objects in, a bundle
out that validates and answers as-of reads. Run: uv run python tests/test_graphiti_adapter.py"""
import pathlib
import sys
import tempfile
from datetime import datetime, timezone
from types import SimpleNamespace as NS

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import factblock  # noqa: E402
from factblock.adapters.graphiti import bundle_from_graphiti, write_bundle  # noqa: E402

T = lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc)  # noqa: E731
g = "user:ann"
nvda = NS(uuid="e-nvda", name="NVDA", group_id=g, labels=["Entity", "Company"], summary="", attributes={}, created_at=T("2024-04-15T00:00:00"))
ceo = NS(uuid="e-ceo", name="Jensen Huang", group_id=g, labels=["Entity", "Person"], summary="", attributes={}, created_at=T("2024-04-15T00:00:00"))
ep = NS(uuid="ep-1", name="turn-1", group_id=g, labels=[], source="message", source_description="chat", content="Jensen runs NVDA",
        valid_at=T("2024-04-10T00:00:00"), created_at=T("2024-04-15T00:00:00"))
fact = NS(uuid="f-1", name="IS_CEO_OF", fact="Jensen Huang is the CEO of NVDA", group_id=g, source_node_uuid="e-ceo", target_node_uuid="e-nvda",
          episodes=["ep-1"], valid_at=T("2024-04-10T00:00:00"), invalid_at=None, expired_at=None, attributes={}, created_at=T("2024-04-15T00:00:00"))
later = NS(uuid="f-2", name="LEADS", fact="NVDA leads the AI chip market", group_id=g, source_node_uuid="e-nvda", target_node_uuid="e-nvda",
           episodes=[], valid_at=T("2024-09-01T00:00:00"), invalid_at=T("2024-08-01T00:00:00"), expired_at=None, attributes={}, created_at=T("2024-09-15T00:00:00"))
mention = NS(source_node_uuid="ep-1", target_node_uuid="e-nvda", group_id=g, created_at=T("2024-04-15T00:00:00"))

res = bundle_from_graphiti([nvda, ceo], [ep], [fact, later], [mention], exported_at=T("2026-10-04T00:00:00"))
assert len(res["manifest"]["declarations"]["backfills"]) == 2, "one batch per distinct created_at"
with tempfile.TemporaryDirectory() as d:
    b = write_bundle(res, d)
    checks = factblock.validate(b)
    assert all(c.ok for c in checks), [c for c in checks if not c.ok]
    may = factblock.scan(b, "2024-05-01")
    assert sorted(may.nodes.column("id").to_pylist()) == ["e-ceo", "e-nvda", "ep-1", "f-1"], may.nodes.column("id").to_pylist()
    assert may.certificate["masked"] == {"node": 1, "edge": 1}      # f-2 and its self-mention are not known yet
    octo = factblock.scan(b, "2024-10-01")
    assert octo.nodes.num_rows == 5 and "masked" not in octo.certificate
    kinds = dict(zip(octo.nodes.column("id").to_pylist(), octo.nodes.column("kind").to_pylist()))
    assert kinds == {"e-ceo": "entity", "e-nvda": "entity", "ep-1": "episode", "f-1": "claim", "f-2": "claim"}
    types = sorted((r["source_id"], r["target_id"], r["edge_type"]) for r in factblock.Bundle(b).edges)
    assert ("f-1", "e-ceo", "MENTIONS") in types and ("f-1", "ep-1", "DERIVED_FROM") in types and ("ep-1", "e-nvda", "MENTIONS") in types
    assert types.count(("f-2", "e-nvda", "MENTIONS")) == 1, "self-referencing fact mentions its entity once"
    f2 = next(n for n in factblock.Bundle(b).nodes if n["id"] == "f-2")
    assert f2.get("valid_to") is None and f2["payload"]["graphiti_invalid_at"], "an invalid_at before valid_at is kept, not applied"
    pq = factblock.write_parquet(b, pathlib.Path(d) / "pq")
    assert all(c.ok for c in factblock.validate(pq))
print("PASS graphiti adapter: 2 batches, validate, scan at two instants, kinds, edges, parquet")
