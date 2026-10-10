"""The one check that fails if track_record breaks: each statement counts once by its latest verdict known on as_of,
open and overdue are told apart, hit rate is right / (right + wrong), and "on record before it was resolved" separates a
row the ledger stamped live from one backfilled with a cited source and one backfilled on the writer's word.
Run: uv run python tests/test_track_record.py"""
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import factblock  # noqa: E402

LIVE = {"ledger": "tckg:test"}   # stamped by a ledger when it happened: written at known_at


def node(i, kind, said, speaker, due=None, attestation=None, source=None):
    p = {"speaker": speaker, **({"source": {"url": source}} if source else {})}
    return {"id": i, "kind": kind, "statement": f"statement {i}", "asserted_at": said, "valid_to": due,
            "known_at": said, "payload": p, **({"attestation": attestation} if attestation else {})}


def verdict(target, outcome, decided):
    return {"target_id": target, "outcome": outcome, "value": outcome, "decided_at": decided, "known_at": decided, "attestation": LIVE}


with tempfile.TemporaryDirectory() as d:
    factblock.write_bundle({"nodes": [
        node("p1", "prediction", "2026-01-05T00:00:00Z", "ana", "2026-03-31T23:59:59Z", LIVE),
        node("p2", "prediction", "2026-01-12T00:00:00Z", "ana", "2026-06-30T23:59:59Z"),
        node("k1", "commitment", "2026-01-20T00:00:00Z", "bo", "2026-02-28T23:59:59Z", source="https://example.com/call"),
        node("p4", "prediction", "2026-01-25T00:00:00Z", "bo", "2026-02-01T23:59:59Z", LIVE),
        node("p5", "prediction", "2026-02-01T00:00:00Z", "bo", "2026-12-31T23:59:59Z", LIVE),
        node("c1", "claim", "2026-02-02T00:00:00Z", "bo", None, LIVE),
    ], "edges": [], "resolutions": [
        verdict("p1", "came_true", "2026-03-28T00:00:00Z"),
        verdict("p2", "did_not", "2026-07-01T00:00:00Z"),
        verdict("k1", "kept", "2026-02-27T00:00:00Z"),
        verdict("p1", "did_not", "2026-05-01T00:00:00Z"),   # re-resolved
    ]}, d)

    r = factblock.track_record(d, "2026-04-01", by="speaker")
    status = {i["id"]: i["status"] for i in r["items"]}
    assert status == {"p1": "right", "p2": "open", "k1": "right", "p4": "overdue", "p5": "open"}, status   # c1: a claim with no verdict
    assert {g["group"]: (g["judged"], g["right"], g["hit_rate"]) for g in r["groups"]} == {"ana": (1, 1, 1.0), "bo": (1, 1, 1.0)}

    r = factblock.track_record(d, "2026-07-02")
    status = {i["id"]: i["status"] for i in r["items"]}
    assert status["p1"] == "wrong" and status["p2"] == "wrong", status   # the later verdict wins once known
    assert r["total"]["judged"] == 3 and r["total"]["hit_rate"] == round(1 / 3, 3), r["total"]
    record = {i["id"]: i["record"] for i in r["items"]}
    assert record == {"p1": "before", "p2": "writer", "k1": "sourced", "p4": None, "p5": None}, record
    assert r["record"] == {"before": 1, "sourced": 1, "writer": 1}

    out = subprocess.run([sys.executable, "-m", "factblock", "track-record", d, "--as-of", "2026-07-02", "--by", "speaker"],
                         capture_output=True, text=True, cwd=ROOT, check=True).stdout
    assert "on record before it was resolved: 1 of 3; 1 written later from a cited source" in out, out
    assert "writer's word" in out, out
    scan = subprocess.run([sys.executable, "-m", "factblock", "scan", d, "--as-of", "2026-07-02"],
                          capture_output=True, text=True, cwd=ROOT, check=True).stdout
    assert "not listed above" in scan and "track-record" in scan, scan

cramer = factblock.track_record(ROOT / "samples" / "cramer", "2026-10-01")
assert (cramer["total"]["right"], cramer["total"]["wrong"]) == (426, 353), cramer["total"]
assert cramer["record"] == {"before": 0, "sourced": 779, "writer": 0}, cramer["record"]   # backfilled from dated recordings

print("PASS track_record: latest verdict as of, open and overdue, hit rate, on record before vs a cited source vs the writer's word, CLI, scan hint, cramer 426/353")
