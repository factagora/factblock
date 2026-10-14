"""Move a bundle between a folder and a store, both ways, without either side inventing a clock.

A store is anything with two methods (the Store protocol below). `TckgStore` talks to a tckg ledger
over HTTP; a store of your own (SQLite, Neo4j, a warehouse) is a class with the same two methods,
and `sync()` never looks past them. The rules a store has to keep are SPEC 6: a row's `known_at`
travels as the backfill batch that attests it, so the store declares the bundle's batches as its
own backfill batches and never adopts an imported row as learned "now".

    sync(bundle, store)                 # push rows the store lacks, pull rows the folder lacks
    sync(bundle, store, push=False)     # pull only: GET /v1/export appended to the folder, or cloned into a new one
"""
import gzip
import io
import json
import tarfile
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from .bundle import Bundle, write_bundle

STRIP = ("known_at", "attestation", "captured_at", "superseded_by", "superseded_for")   # the store stamps these; a client sending them is refused


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


def _json(rows):
    return json.loads(json.dumps(rows, default=_iso))


def _instant(v):
    """One spelling per instant, so a key built from a parsed datetime matches one built from a ledger's
    string ("...57.893320+00:00" and "...57.89332Z" are the same edge)."""
    d = v if isinstance(v, datetime) else datetime.fromisoformat(v.replace("Z", "+00:00"))
    return d.astimezone(timezone.utc).isoformat()


def node_key(r):
    return ("node", r["id"])


def edge_key(r):
    return ("edge", r["source_id"], r["target_id"], r["edge_type"], _instant(r["asserted_at"]))


def resolution_key(r):
    return ("resolution", r["target_id"], _instant(r["decided_at"]))


KEYS = {"nodes": node_key, "edges": edge_key, "resolutions": resolution_key}


class Store(Protocol):
    def pull(self, as_of: str) -> dict:
        """{"manifest", "nodes", "edges", "resolutions"}: the store as a bundle, rows known at or before as_of."""

    def push(self, manifest: dict, nodes: list[dict], edges: list[dict]) -> dict:
        """Write rows under the batches `manifest["declarations"]["backfills"]` declares, after the facts
        `manifest["declarations"]["facts"]` declares (only the ones the store lacks; a store may ignore them).
        Returns {"accepted": int, "skipped": [..], "refused": [..]}."""


def batches_of(manifest: dict, rows: list[dict]) -> dict[str, dict]:
    """Batch name -> {declared_known_at, reason}. Declared batches come from the manifest; a row another
    ledger stamped (attestation.batch null) gets a batch at its own known_at, named after that ledger,
    so its knowledge time survives the move (SPEC 6)."""
    out = {b["batch"]: {"declared_known_at": _iso(b["declared_known_at"]), "reason": b.get("reason") or f"import of batch {b['batch']}"}
           for b in manifest.get("declarations", {}).get("backfills", [])}
    for r in rows:
        a = r.get("attestation") or {}
        if not a.get("batch"):
            name = f"{a.get('ledger', 'unknown')}@{_iso(r['known_at'])}"
            r["attestation"] = {**a, "batch": name}
            out.setdefault(name, {"declared_known_at": _iso(r["known_at"]), "reason": f"imported rows that {a.get('ledger', 'another ledger')} stamped known at {_iso(r['known_at'])}"})
    return out


def latest_facts(manifest: dict) -> dict[str, dict]:
    """fact_key -> its latest declaration (SPEC 3.7)."""
    facts = manifest.get("declarations", {}).get("facts", [])
    return {f["fact_key"]: f for f in sorted(facts, key=lambda f: _instant(f["declared_at"]) if f.get("declared_at") else "")}


def _rule(f):
    return {"key_fields": list(f.get("key_fields") or []), "policy": f.get("policy") or "latest_valid", "source_order": f.get("source_order")}


class TckgStore:
    """A tckg ledger: pull is GET /v1/export, push is one POST /v1/memories per (batch, space), each
    declaring that batch as a backfill. Needs the API key of the tenant and, for rows that carry no
    `space`, a default space."""

    def __init__(self, url: str, token: str, space: str | None = None, timeout: int = 300):
        self.url, self.token, self.space, self.timeout = url.rstrip("/"), token, space, timeout

    def _call(self, method, path, body=None, params=None):
        q = "?" + urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None}) if params else ""
        req = urllib.request.Request(self.url + path + q, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.read()

    def pull(self, as_of):
        raw = self._call("GET", "/v1/export", params={"as_of": as_of, "space": self.space})
        files = {}
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
            for m in tar.getmembers():
                if m.isfile():
                    files[Path(m.name).name] = tar.extractfile(m).read().decode()
        rows = lambda name: [json.loads(l) for l in files.get(name, "").splitlines() if l.strip()]  # noqa: E731
        return {"manifest": json.loads(files["factblock.json"]), "nodes": rows("nodes.jsonl"), "edges": rows("edges.jsonl"), "resolutions": rows("resolutions.jsonl")}

    def push(self, manifest, nodes, edges):
        nodes, edges = _json(nodes), _json(edges)
        batches = batches_of(manifest, nodes + edges)
        groups = defaultdict(lambda: {"nodes": [], "edges": []})
        for n in nodes:
            groups[(n["attestation"]["batch"], n.get("space") or self.space)]["nodes"].append(n)
        for e in edges:
            groups[(e["attestation"]["batch"], e.get("space") or self.space)]["edges"].append(e)
        report = {"accepted": 0, "skipped": [], "refused": [], "batches": 0, "facts": 0}
        # Facts first, so the rows that carry a fact_key arrive declared. tckg stamps declared_at itself.
        # shortcut: declared_at on the ledger is the sync instant, so resolve at an earlier as_of says
        # undeclared_fact unless rules_as_of is passed; upgrade when tckg takes a declared instant for facts.
        for f in _json(manifest.get("declarations", {}).get("facts", [])):
            try:
                self._call("POST", "/v1/facts", {k: f[k] for k in ("fact_key", "key_fields", "policy", "source_order") if f.get(k) is not None})
                report["facts"] += 1
            except urllib.error.HTTPError as e:
                report["refused"].append({"fact_key": f["fact_key"], "status": e.code, "error": e.read().decode(errors="replace")[:300]})
        # ponytail: one POST per (batch, space), ordered by knowledge time so an edge never arrives before its endpoints.
        for (batch, space), g in sorted(groups.items(), key=lambda kv: batches[kv[0][0]]["declared_known_at"]):
            if space is None:
                raise ValueError("rows without a space: pass space= to TckgStore (whose memory this is)")
            body = {"space": space, "backfill": {"declared_captured_at": batches[batch]["declared_known_at"], "reason": batches[batch]["reason"]},
                    "nodes": [{k: v for k, v in n.items() if k not in STRIP} for n in g["nodes"]],
                    "edges": [{k: v for k, v in e.items() if k not in STRIP} for e in g["edges"]]}
            r = json.loads(self._call("POST", "/v1/memories", body))
            report["accepted"] += r.get("accepted", 0)
            report["skipped"] += [w for w in r.get("warned", []) if w.get("reason") == "already_remembered"]
            report["refused"] += r.get("refused", [])
            report["batches"] += 1
        return report


def sync(bundle, store: Store, as_of=None, push=True, pull=True) -> dict:
    """Two-way by identity: nodes by id, edges by (source, target, type, asserted_at), resolutions by
    (target, decided_at). Rows only the folder has go to the store; rows only the store has are
    appended to the folder with the store's own known_at and batches. Nothing is ever changed in place."""
    path = Path(bundle.path if isinstance(bundle, Bundle) else bundle)
    exists = (path / "factblock.json").exists()
    b = bundle if isinstance(bundle, Bundle) else (Bundle(path) if exists else None)   # no folder yet: a pull clones it
    now = datetime.now(timezone.utc).isoformat()
    remote = store.pull(as_of or now)
    as_of = as_of or now
    local = {"nodes": b.nodes, "edges": b.edges, "resolutions": b.resolutions} if b else {"nodes": [], "edges": [], "resolutions": []}
    have_remote = {t: {KEYS[t](r) for r in remote.get(t, [])} for t in KEYS}
    have_local = {t: {KEYS[t](r) for r in local[t]} for t in KEYS}
    # the store's namespace (tckg: "<tenant>/<space>") and how many rows it had, so an empty pull can say whose store was empty
    out = {"as_of": as_of, "pushed": None, "pulled": None,
           "store": {"namespace": remote["manifest"].get("namespace"), "rows": sum(len(remote.get(t, [])) for t in KEYS)}}
    if push:
        only_local = {t: [r for r in local[t] if KEYS[t](r) not in have_remote[t]] for t in KEYS}
        # A fact the store declared differently stays as the store has it: sync never changes a rule in place.
        # Compared with the store's rules as of now, not as_of: a rule the store declared after a past
        # as_of is still the one a POST would replace.
        rules = remote if as_of == now else store.pull(now)
        mine, theirs = latest_facts(b.manifest) if b else {}, latest_facts(rules["manifest"])
        new_facts = [f for k, f in mine.items() if k not in theirs]
        manifest = {**b.manifest, "declarations": {**b.manifest.get("declarations", {}), "facts": new_facts}} if b else {}
        out["pushed"] = store.push(manifest, only_local["nodes"], only_local["edges"]) if only_local["nodes"] or only_local["edges"] or new_facts \
            else {"accepted": 0, "skipped": [], "refused": [], "batches": 0}
        out["pushed"].setdefault("facts", 0)
        out["pushed"]["facts_differ"] = [{"fact_key": k, "local": _rule(mine[k]), "store": _rule(theirs[k])}
                                         for k in sorted(mine) if k in theirs and _rule(mine[k]) != _rule(theirs[k])]
        out["pushed"]["resolutions_not_pushed"] = len(only_local["resolutions"])   # verdicts are the store's to make
    if pull:
        only_remote = {t: [r for r in remote.get(t, []) if KEYS[t](r) not in have_local[t]] for t in KEYS}
        if any(only_remote.values()) or not exists:
            write_bundle({"manifest": remote["manifest"], **only_remote}, path, append=exists)
        out["pulled"] = {t: len(v) for t, v in only_remote.items()}
    return out
