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
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import factblock  # noqa: E402
import factblock.__main__ as fbmain  # noqa: E402
from factblock.sync import KEYS, batch_key, batches_of  # noqa: E402

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
            facts = [f for f in self.facts if f["declared_at"] <= params["as_of"]]   # a ledger exports the rules declared by as_of
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                data = json.dumps({"factblock_version": "1.0-draft.1", "namespace": self.namespace, "source": "tckg/test",
                                   "declarations": {"facts": facts, "backfills": [], "edge_types": []}}).encode()
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
assert r["pushed"]["facts"] == 1 and r["pushed"]["facts_differ"] == [{"fact_key": "belief:fed:direction",
    "local": {"key_fields": ["subject"], "policy": "latest_valid", "source_order": None},
    "store": {"key_fields": ["subject"], "policy": "strict", "source_order": None}}], r["pushed"]
assert [x["fact_key"] for x in r["pushed"]["refused"]] == ["belief:nvda:direction"], r["pushed"]["refused"]
assert r["store"] == {"namespace": "acme/brain", "rows": 0}, r["store"]

# 5b. a past as_of still compares against the ledger's rules now: a rule declared after as_of is not overwritten
later = {**fed, "key_fields": ["subject", "other"], "policy": "latest_valid", "declared_at": "2026-10-01T00:00:00Z"}
t = FakeTckg("acme/brain", facts=[later])
r = factblock.sync(work, t, as_of="2025-01-01", pull=False)
assert [d["fact_key"] for d in r["pushed"]["facts_differ"]] == ["belief:fed:direction"], r["pushed"]
assert "belief:fed:direction" not in [b["fact_key"] for m, p, b in t.calls if p == "/v1/facts"] and t.facts == [later], t.calls

# 5c. a folder that does not exist yet, synced both ways with an empty store: nothing to push, an empty clone
r = factblock.sync(work.parent / "new", DictStore())
assert r["pushed"]["accepted"] == 0 and r["pushed"]["facts"] == 0 and (work.parent / "new" / "factblock.json").exists(), r

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

# 6b. CLI push: the summary says what was declared, and a differing rule shows both sides and what to do
fbmain.TckgStore = lambda url, token, space: FakeTckg(f"acme/{space}", facts=[fed])
out = io.StringIO()
sys.argv = ["factblock", "sync", str(work), "https://ledger.test", "--space", "brain", "--token", "k", "--push-only"]
with contextlib.redirect_stdout(out):
    try:
        fbmain.main()
    except SystemExit as e:
        assert e.code in (0, None), e.code
text = out.getvalue()
assert "declared 2 fact rules (fact_key)" in text, text
assert ("fact belief:fed:direction: the ledger has key_fields ['subject'], policy strict; the folder has key_fields ['subject'], policy latest_valid. "
        "Kept the ledger's rule; to use the folder's, declare it again on the ledger (POST /v1/facts).") in text, text
# 6c. an older ledger gets today's requests: GET /v1/version first, then one POST per batch declaring it
t = FakeTckg("acme/brain")
factblock.sync(work, t, pull=False)
mem = [b for m, p, b in t.calls if p == "/v1/memories"]
assert ("GET", "/v1/version", None) in t.calls and len(mem) == 4 and all("backfill" in b and "backfills" not in b for b in mem), mem
assert not any("batch" in r for b in mem for r in b["nodes"] + b["edges"]), mem


# 7. keyed batches (tckg 0.3.12): a ledger that declares a batch once per key, as the server does
class Ledger(factblock.TckgStore):
    def __init__(self, version="0.3.12", lose=0):
        super().__init__("https://ledger.test", "key", "brain")
        self.version, self.lose = version, lose        # lose: how many responses to drop after writing
        self.keys, self.batches, self.rows, self.posts = {}, 0, {"nodes": [], "edges": []}, []

    def _call(self, method, path, body=None, params=None):
        if path == "/v1/version":
            if isinstance(self.version, Exception):
                raise self.version
            return json.dumps({"version": self.version}).encode()
        if path == "/v1/export":
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                for name, data in [("factblock.json", {"factblock_version": "1.0-draft.1", "namespace": "acme/brain", "declarations": {"facts": [], "backfills": []}}),
                                   ("nodes.jsonl", self.rows["nodes"]), ("edges.jsonl", self.rows["edges"])]:
                    raw = (json.dumps(data) if name.endswith(".json") else "".join(json.dumps(r) + "\n" for r in data)).encode()
                    info = tarfile.TarInfo("factblock/" + name); info.size = len(raw)
                    tar.addfile(info, io.BytesIO(raw))
            return buf.getvalue()
        if path == "/v1/facts":
            return b"{}"
        self.posts.append(body)
        out = {"accepted": 0, "warned": [], "refused": [], "backfill_batches": {}}
        for bf in body.get("backfills", []):
            content = (bf["declared_captured_at"], bf["reason"])
            if self.keys.setdefault(bf["key"], content) != content:
                raise urllib.error.HTTPError(self.url + path, 409, "Conflict", {}, io.BytesIO(b'{"detail": {"error": "TCKG_BATCH_KEY_CONFLICT"}}'))
        for bf in body.get("backfills", []):
            out["backfill_batches"][bf["key"]] = "id-" + bf["key"]
        self.batches = len(self.keys) + sum(1 for b in self.posts if b.get("backfill"))
        have = {KEYS[t](r) for t in self.rows for r in self.rows[t]}
        for t in ("nodes", "edges"):
            for r in body[t]:
                if r.get("batch") is not None and r["batch"] not in self.keys:
                    out["refused"].append({"id": r.get("id"), "reason": "unknown_batch"})
                elif KEYS[t](r) in have:
                    out["warned"].append({"id": r.get("id"), "reason": "already_remembered"})
                else:
                    self.rows[t].append(r); out["accepted"] += 1
        if self.lose:
            self.lose -= 1
            raise urllib.error.URLError("connection reset")   # written, response lost
        return json.dumps(out).encode()


rates = factblock.Bundle(work)
# the key is a pure function of the batch: one spelling per instant, and a name that differs only in content gets its own key
k = batch_key("b1", {"declared_known_at": "2024-04-15T00:00:00Z", "reason": "r"})
assert k == batch_key("b1", {"declared_known_at": datetime(2024, 4, 15, tzinfo=timezone.utc), "reason": "r"}) and k.startswith("b1#"), k
assert k != batch_key("b1", {"declared_known_at": "2024-04-15T00:00:00Z", "reason": "other"})
assert len(batch_key("x" * 500, {"declared_known_at": "2024-04-15T00:00:00Z", "reason": "r"})) <= 200

# the version gate compares numbers: 0.3.9 is older than 0.3.12, an unreadable or unreachable version is old
for v, keyed in [("0.3.9", False), ("0.3.11", False), ("0.3.12", True), ("0.3.13", True), ("0.4.0", True), ("1.0.0", True),
                 ("", False), ("dev", False), (urllib.error.URLError("down"), False)]:
    led = Ledger(version=v)
    led.push(rates.manifest, rates.nodes, rates.edges)
    assert all(("backfills" in b) == keyed and ("backfill" in b) != keyed for b in led.posts), (v, led.posts)

# one request for the whole folder: every batch declared by key, every row naming its batch
led = Ledger()
r = led.push(rates.manifest, rates.nodes, rates.edges)
assert len(led.posts) == 1 and r["batches"] == 4 and r["accepted"] == 10 and not r["refused"], r
assert {bf["key"].split("#")[0] for bf in led.posts[0]["backfills"]} == {"b1", "b2", "b3", "dictstore/0@2024-11-02T00:00:00+00:00"}, led.posts[0]["backfills"]
assert {r["batch"] for r in led.posts[0]["nodes"] + led.posts[0]["edges"]} == {bf["key"] for bf in led.posts[0]["backfills"]}, led.posts[0]

# a second push of the same rows declares no new batch and writes nothing (SPEC 6.1: re-import is a no-op)
before = led.batches
r = led.push(rates.manifest, rates.nodes, rates.edges)
assert led.batches == before == 4 and r["accepted"] == 0 and len(r["skipped"]) == 10 and not r["refused"], (led.batches, r)

# a retry after a lost response gets the batches the first try declared
led = Ledger(lose=1)
try:
    led.push(rates.manifest, rates.nodes, rates.edges)
    raise AssertionError("the lost response should surface")
except urllib.error.URLError:
    pass
r = led.push(rates.manifest, rates.nodes, rates.edges)
assert led.batches == 4 and r["accepted"] == 0 and len(r["skipped"]) == 10, (led.batches, r)

# sync twice: the second sync sends nothing
led = Ledger()
assert factblock.sync(work, led, pull=False)["pushed"]["accepted"] == 10
assert factblock.sync(work, led, pull=False)["pushed"]["batches"] == 0 and len(led.posts) == 1 and led.batches == 4

# packing: at most 1000 batches per request, in knowledge order, and a request stops near 2000 rows
many = {"declarations": {"backfills": [{"batch": f"d{i:04d}", "declared_known_at": f"2020-01-01T00:00:{i % 60:02d}Z", "reason": "r"} for i in range(2500)]}}
nodes = [{"id": f"n{i}", "kind": "claim", "statement": "s", "asserted_at": "2019-01-01T00:00:00Z", "attestation": {"batch": f"d{i:04d}"}} for i in range(2500)]
led = Ledger()
r = led.push(many, nodes, [])
assert [len(b["backfills"]) for b in led.posts] == [1000, 1000, 500] and r["batches"] == 2500 and r["accepted"] == 2500, [len(b["backfills"]) for b in led.posts]
known = [bf["declared_captured_at"] for b in led.posts for bf in b["backfills"]]
assert known == sorted(known), "requests go in knowledge order"
big = [{**n, "id": f"m{i}", "attestation": {"batch": f"d{i % 3:04d}"}} for i, n in enumerate(nodes[:2400])]   # 3 batches of 800 rows
led = Ledger()
led.push(many, big, [])
assert [len(b["nodes"]) for b in led.posts] == [1600, 800], [len(b["nodes"]) for b in led.posts]

print("PASS sync: push 9, no-op, pull verdict + store-stamped row, folder valid, re-push declares known_at as a batch, "
      "keyed batches from tckg 0.3.12 (one request, re-push and retry declare nothing new, packed by 1000), "
      "facts declared once and never redeclared over the ledger's, tenant and space in the CLI line, empty pull explained")
