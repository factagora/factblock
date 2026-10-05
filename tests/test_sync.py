"""The one check that fails if sync breaks, against an in-memory store that is also the smallest
example of bringing your own store: two methods, and known_at travels as batches (SPEC 6).
Run: uv run python tests/test_sync.py"""
import json
import pathlib
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import factblock  # noqa: E402
from factblock.sync import KEYS, batches_of  # noqa: E402

RATES = pathlib.Path(__file__).resolve().parents[1] / "samples" / "rates"


class DictStore:
    """A store is a dict of tables plus the batches it has declared. It refuses rows that try to
    carry known_at themselves and stamps each row with its batch's declared instant, like a ledger."""

    def __init__(self):
        self.batches, self.rows = {}, {"nodes": [], "edges": [], "resolutions": []}

    def pull(self, as_of):
        manifest = {"factblock_version": "1.0-draft.1", "namespace": "dictstore", "source": "dictstore/0",
                    "declarations": {"facts": [], "edge_types": [],
                                     "backfills": [{"batch": k, "declared_known_at": v["declared_known_at"], "reason": v["reason"],
                                                    "declared_by": "process:dictstore", "captured_at": "2026-10-05T00:00:00+00:00"} for k, v in self.batches.items()]}}
        vis = lambda t: [r for r in self.rows[t] if r["known_at"] <= as_of]  # noqa: E731
        return {"manifest": manifest, "nodes": vis("nodes"), "edges": vis("edges"), "resolutions": vis("resolutions")}

    def push(self, manifest, nodes, edges):
        rows = json.loads(json.dumps(nodes + edges, default=lambda d: d.isoformat()))
        self.batches.update(batches_of(manifest, rows))
        have = {KEYS[t](r) for t in ("nodes", "edges") for r in self.rows[t]}
        n = 0
        for r in rows:
            r = {k: v for k, v in r.items() if k != "known_at"}
            b = self.batches[r["attestation"]["batch"]]
            r["known_at"] = b["declared_known_at"]
            r["attestation"] = {"ledger": "dictstore/0", "batch": r["attestation"]["batch"]}
            t = "nodes" if "id" in r else "edges"
            if KEYS[t](r) not in have:
                self.rows[t].append(r); n += 1
        return {"accepted": n, "skipped": [], "refused": [], "batches": len(self.batches)}


work = pathlib.Path(tempfile.mkdtemp()) / "rates"
shutil.copytree(RATES, work)
store = DictStore()

# 1. first sync: the whole folder goes up, nothing comes down
r = factblock.sync(work, store)
assert r["pushed"]["accepted"] == 9 and r["pulled"] == {"nodes": 0, "edges": 0, "resolutions": 0}, r
assert set(store.batches) == {"b1", "b2", "b3"} and store.rows["nodes"][0]["known_at"] == "2024-04-15T00:00:00+00:00"

# 2. second sync is a no-op: identity, not attestation, decides what is new
r = factblock.sync(work, store)
assert r["pushed"]["accepted"] == 0 and r["pulled"] == {"nodes": 0, "edges": 0, "resolutions": 0}, r

# 3. the store learns something (a verdict and a row stamped by the store itself); pull appends it, folder stays valid
store.batches["v1"] = {"declared_known_at": "2024-11-01T00:00:00+00:00", "reason": "verdicts"}
store.rows["resolutions"].append({"target_id": "c1", "value": {"direction": "up"}, "outcome": "true", "method": "price", "ruleset": "r1",
                                  "resolver": "process:dictstore", "decided_at": "2024-11-01T00:00:00+00:00",
                                  "known_at": "2024-11-01T00:00:00+00:00", "attestation": {"ledger": "dictstore/0", "batch": "v1"}})
store.rows["nodes"].append({"id": "x1", "kind": "claim", "statement": "Stamped by the store", "asserted_at": "2024-11-02T00:00:00+00:00",
                            "valid_from": "2024-11-02T00:00:00+00:00", "valid_to": None, "known_at": "2024-11-02T00:00:00+00:00",
                            "attestation": {"ledger": "dictstore/0", "batch": None}})
r = factblock.sync(work, store)
assert r["pushed"]["accepted"] == 0 and r["pulled"] == {"nodes": 1, "edges": 0, "resolutions": 1}, r
b = factblock.Bundle(work)
assert len(b.nodes) == 7 and len(b.resolutions) == 1 and "v1" in b.backfills
checks = factblock.validate(b)
assert all(c.ok for c in checks), [c for c in checks if not c.ok]
assert factblock.scan(work, "2024-10-15").resolutions.num_rows == 0 and factblock.scan(work, "2024-11-05").resolutions.num_rows == 1

# 4. pushing the folder into a second, empty store carries the pulled rows too: the store-stamped row
#    becomes a batch at its own known_at (SPEC 6), never a fresh row
second = DictStore()
r = factblock.sync(work, second, pull=False)
assert r["pushed"]["accepted"] == 10 and r["pushed"]["resolutions_not_pushed"] == 1, r
assert any(k.startswith("dictstore/0@2024-11-02") for k in second.batches), second.batches
assert factblock.sync(work, second)["pulled"] == {"nodes": 0, "edges": 0, "resolutions": 0}
print("PASS sync: push 9, no-op, pull verdict + store-stamped row, folder valid, re-push declares known_at as a batch")
