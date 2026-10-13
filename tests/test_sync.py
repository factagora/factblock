"""The one check that fails if sync breaks, against an in-memory store that is also the smallest
example of bringing your own store: two methods, and known_at travels as batches (SPEC 6).
Run: uv run python tests/test_sync.py"""
import contextlib
import io
import json
import pathlib
import shutil
import sys
import tarfile
import tempfile
import urllib.error

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import factblock  # noqa: E402
import factblock.__main__ as fbmain  # noqa: E402
from factblock.sync import KEYS, batches_of  # noqa: E402

RATES = pathlib.Path(__file__).resolve().parents[1] / "samples" / "rates"


class DictStore:
    """A store is a dict of tables plus the batches it has declared. It refuses rows that try to
    carry known_at themselves and stamps each row with its batch's declared instant, like a ledger."""

    def __init__(self):
        self.batches, self.rows, self.facts = {}, {"nodes": [], "edges": [], "resolutions": []}, []

    def pull(self, as_of):
        manifest = {"factblock_version": "1.0-draft.1", "namespace": "dictstore", "source": "dictstore/0",
                    "declarations": {"facts": self.facts, "edge_types": [],
                                     "backfills": [{"batch": k, "declared_known_at": v["declared_known_at"], "reason": v["reason"],
                                                    "declared_by": "process:dictstore", "captured_at": "2026-10-05T00:00:00+00:00"} for k, v in self.batches.items()]}}
        vis = lambda t: [r for r in self.rows[t] if r["known_at"] <= as_of]  # noqa: E731
        return {"manifest": manifest, "nodes": vis("nodes"), "edges": vis("edges"), "resolutions": vis("resolutions")}

    def push(self, manifest, nodes, edges):
        rows = json.loads(json.dumps(nodes + edges, default=lambda d: d.isoformat()))
        self.facts += json.loads(json.dumps(manifest["declarations"]["facts"], default=lambda d: d.isoformat()))
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
assert r["pushed"]["facts"] == 0 and {f["fact_key"] for f in store.facts} == {"belief:fed:direction", "belief:tsla:direction", "belief:nvda:direction"}, r
assert set(store.batches) == {"b1", "b2", "b3"} and store.rows["nodes"][0]["known_at"] == "2024-04-15T00:00:00+00:00"

# 2. second sync is a no-op: identity, not attestation, decides what is new
r = factblock.sync(work, store)
assert r["pushed"]["accepted"] == 0 and r["pulled"] == {"nodes": 0, "edges": 0, "resolutions": 0}, r
assert len(store.facts) == 3, store.facts   # facts the store already declares are not sent again

# 2b. a ledger may spell an instant differently ("Z", trimmed microseconds); same edge, still a no-op
for e in store.rows["edges"]:
    e["asserted_at"] = e["asserted_at"].replace("+00:00", "Z")
r = factblock.sync(work, store)
assert r["pushed"]["batches"] == 0 and r["pulled"] == {"nodes": 0, "edges": 0, "resolutions": 0}, r
for e in store.rows["edges"]:
    e["asserted_at"] = e["asserted_at"].replace("Z", "+00:00")

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
assert len(b.nodes) == 7 and len(b.resolutions) == 4 and "v1" in b.backfills   # 3 sample verdicts + the pulled one
checks = factblock.validate(b)
assert all(c.ok for c in checks), [c for c in checks if not c.ok]
assert factblock.scan(work, "2024-10-15").resolutions.num_rows == 2 and factblock.scan(work, "2024-11-05").resolutions.num_rows == 3

# 4. pushing the folder into a second, empty store carries the pulled rows too: the store-stamped row
#    becomes a batch at its own known_at (SPEC 6), never a fresh row
second = DictStore()
r = factblock.sync(work, second, pull=False)
assert r["pushed"]["accepted"] == 10 and r["pushed"]["resolutions_not_pushed"] == 4, r
assert any(k.startswith("dictstore/0@2024-11-02") for k in second.batches), second.batches
assert factblock.sync(work, second)["pulled"] == {"nodes": 0, "edges": 0, "resolutions": 0}

# 5. TckgStore over a fake ledger: facts go to POST /v1/facts before the rows, a fact the ledger declares
#    differently is left alone, and the result names the ledger's namespace (tckg: tenant/space)
class FakeTckg(factblock.TckgStore):
    def __init__(self, namespace, facts=(), refuse=()):
        super().__init__("https://ledger.test", "key", "brain")
        self.namespace, self.facts, self.refuse, self.calls = namespace, list(facts), set(refuse), []

    def _call(self, method, path, body=None, params=None):
        self.calls.append((method, path, body))
        if path == "/v1/export":
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                data = json.dumps({"factblock_version": "1.0-draft.1", "namespace": self.namespace, "source": "tckg/test",
                                   "declarations": {"facts": self.facts, "backfills": [], "edge_types": []}}).encode()
                info = tarfile.TarInfo("factblock/factblock.json"); info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            return buf.getvalue()
        if path == "/v1/facts" and body["fact_key"] in self.refuse:
            raise urllib.error.HTTPError(self.url + path, 400, "Bad Request", {}, io.BytesIO(b'{"error": "TCKG_SOURCE_ORDER_REQUIRED"}'))
        return json.dumps({"accepted": len(body.get("nodes", [])) + len(body.get("edges", []))} if path == "/v1/memories" else {}).encode()


fed = {"fact_key": "belief:fed:direction", "key_fields": ["subject"], "policy": "strict", "source_order": None, "declared_at": "2026-01-01T00:00:00Z"}
t = FakeTckg("acme/brain", facts=[fed], refuse={"belief:nvda:direction"})
r = factblock.sync(work, t, push=True, pull=False)
posts = [(p, b) for m, p, b in t.calls if m == "POST"]
assert [b["fact_key"] for p, b in posts if p == "/v1/facts"] == ["belief:tsla:direction", "belief:nvda:direction"], posts
assert posts[0][0] == "/v1/facts" and posts[0][1] == {"fact_key": "belief:tsla:direction", "key_fields": ["subject"], "policy": "latest_valid"}, posts[0]
assert r["pushed"]["facts"] == 1 and r["pushed"]["facts_differ"] == ["belief:fed:direction"], r["pushed"]
assert [x["fact_key"] for x in r["pushed"]["refused"]] == ["belief:nvda:direction"], r["pushed"]["refused"]
assert r["store"] == {"namespace": "acme/brain", "rows": 0}, r["store"]

# 6. CLI: the summary names tenant and space, and an empty pull says whose space was empty
fbmain.TckgStore = lambda url, token, space: FakeTckg(f"acme/{space}")
out = io.StringIO()
sys.argv = ["factblock", "sync", str(work.parent / "clone"), "https://ledger.test", "--space", "other", "--token", "k", "--pull-only"]
with contextlib.redirect_stdout(out):
    try:
        fbmain.main()
    except SystemExit as e:
        assert e.code in (0, None), e.code
text = out.getvalue()
assert "(tenant acme, space other)" in text and "pulled 0 nodes" in text and "had no rows for tenant acme, space other" in text, text
print("PASS sync: push 9, no-op, pull verdict + store-stamped row, folder valid, re-push declares known_at as a batch, "
      "facts declared once and never redeclared over the ledger's, tenant and space in the CLI line, empty pull explained")
