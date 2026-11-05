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
    assert r["record_vouched_by"] == {"tckg:test": 1} and {i["id"]: i["vouched_by"] for i in r["items"]}["p2"] == "process:factblock-write"

    out = subprocess.run([sys.executable, "-m", "factblock", "track-record", d, "--as-of", "2026-07-02", "--by", "speaker"],
                         capture_output=True, text=True, cwd=ROOT, check=True).stdout
    assert "on record before it was resolved: 1 of 3; 1 written later from a cited source" in out, out
    assert "writer's word" in out, out
    assert "on whose word it was written then: tckg:test 1" in out, out
    picked = factblock.track_record(d, "2026-07-02", ids=["p1", "k1", "c1"])   # the record of calls like these
    assert {i["id"] for i in picked["items"]} == {"p1", "k1"} and picked["left_out"] == 1, picked   # c1: a claim nobody judged
    assert factblock.track_record(d, "2026-07-02", speaker="ANA")["total"]["judged"] == 2
    try:
        factblock.track_record(d, "2026-01-01", ids=["p5"])   # said on 02-01: not known yet
        raise AssertionError("an id unknown as of as_of must be refused")
    except ValueError as e:
        assert "p5" in str(e)
    out = subprocess.run([sys.executable, "-m", "factblock", "track-record", d, "--as-of", "2026-07-02", "--ids", "p1,k1,c1"],
                         capture_output=True, text=True, cwd=ROOT, check=True).stdout
    assert "left out: 1 picked statement" in out, out
    scan = subprocess.run([sys.executable, "-m", "factblock", "scan", d, "--as-of", "2026-07-02"],
                          capture_output=True, text=True, cwd=ROOT, check=True).stdout
    assert "not listed above" in scan and "track-record" in scan, scan

with tempfile.TemporaryDirectory() as d:   # who vouches: a batch captured before the verdict counts as before, on its declarer's word (SPEC 3.4)
    early = {"batch": "collector-0105", "declared_known_at": "2026-01-05T00:00:00Z", "reason": "first seen by the collector",
             "declared_by": "process:collector", "captured_at": "2026-01-05T00:10:00Z"}
    factblock.write_bundle({"manifest": {"declarations": {"backfills": [early]}}, "nodes": [
        node("q1", "prediction", "2026-01-05T00:00:00Z", "ana", "2026-03-31T23:59:59Z", {"batch": "collector-0105"}),
        node("q2", "prediction", "2026-01-05T00:00:00Z", "ana", "2026-03-31T23:59:59Z", LIVE)],
        "resolutions": [verdict("q1", "came_true", "2026-03-01T00:00:00Z"), verdict("q2", "did_not", "2026-03-01T00:00:00Z")]}, d)
    r = factblock.track_record(d, "2026-04-01")
    assert r["record"]["before"] == 2 and r["record_vouched_by"] == {"process:collector": 1, "tckg:test": 1}, r["record_vouched_by"]
    out = subprocess.run([sys.executable, "-m", "factblock", "track-record", d, "--as-of", "2026-04-01"], capture_output=True, text=True, cwd=ROOT, check=True).stdout
    assert "on record before it was resolved: 2 of 2\n  on whose word it was written then: process:collector 1, tckg:test 1" in out, out

cramer = factblock.track_record(ROOT / "samples" / "cramer", "2026-10-01")
assert (cramer["total"]["right"], cramer["total"]["wrong"]) == (426, 353), cramer["total"]
assert cramer["record"] == {"before": 0, "sourced": 779, "writer": 0} and cramer["record_vouched_by"] == {}, cramer["record"]
bl = cramer["total"]["baseline"]   # 54.7% right, but "up" every time would have been 53.8%
assert (bl["n"], bl["always_up_hit_rate"], bl["avg_excess_if_followed"]) == (779, 0.538, 0.0136), bl
assert "baseline" not in factblock.track_record(ROOT / "samples" / "rates", "2025-01-01")["total"]   # verdicts without a return

with tempfile.TemporaryDirectory() as d:   # a tckg export carries the verdict value as a JSON string
    factblock.write_bundle({"nodes": [node("s1", "prediction", "2026-01-05T00:00:00Z", "ana", "2026-02-05T23:59:59Z", LIVE, None) | {"payload": {"direction": "down"}}],
                            "edges": [], "resolutions": [{**verdict("s1", "came_true", "2026-02-06T00:00:00Z"), "value": '{"return": -0.04, "excess_over_spy": -0.01}'}]}, d)
    bl = factblock.track_record(d, "2026-03-01")["total"]["baseline"]
    assert bl == {"n": 1, "always_up_hit_rate": 0.0, "avg_return_if_followed": 0.04, "avg_excess_if_followed": 0.01, "benchmarks": {"SPY": 1}}, bl   # short a fall

with tempfile.TemporaryDirectory() as d:   # excess over a named benchmark; excess_over_spy still reads as SPY; mixed benchmarks are named
    calls = [("k1", '{"return": 0.05, "excess": 0.012, "benchmark": "069500"}'), ("k2", {"return": 0.03, "excess": 0.008, "benchmark": "069500"}),
             ("k3", {"return": 0.02, "excess_over_spy": 0.004}), ("k4", {"return": 0.01, "excess": 0.002, "excess_over_spy": 0.9}),
             ("k5", {"return": 0.01})]
    factblock.write_bundle({"nodes": [node(k, "prediction", "2026-01-05T00:00:00Z", "ana", "2026-02-05T23:59:59Z", LIVE, None) | {"payload": {"direction": "up"}} for k, _ in calls],
                            "edges": [], "resolutions": [{**verdict(k, "came_true", "2026-02-06T00:00:00Z"), "value": val} for k, val in calls]}, d)
    r = factblock.track_record(d, "2026-03-01")
    assert [(i["excess"], i["benchmark"]) for i in r["items"]] == [(0.012, "069500"), (0.008, "069500"), (0.004, "SPY"), (0.002, "unnamed"), (None, None)], r["items"]
    bl = r["total"]["baseline"]
    assert bl["avg_excess_if_followed"] == 0.0065 and bl["benchmarks"] == {"069500": 2, "SPY": 1, "unnamed": 1}, bl
    out = subprocess.run([sys.executable, "-m", "factblock", "track-record", d, "--as-of", "2026-03-01"], capture_output=True, text=True, cwd=ROOT, check=True).stdout
    assert "+0.7% over 069500 2, SPY 1, unnamed 1\n" in out, out
    factblock.write_bundle({"nodes": [node("k1", "prediction", "2026-01-05T00:00:00Z", "ana", "2026-02-05T23:59:59Z", LIVE, None) | {"payload": {"direction": "up"}}],
                            "edges": [], "resolutions": [{**verdict("k1", "came_true", "2026-02-06T00:00:00Z"), "value": calls[0][1]}]}, d + "/one")
    out = subprocess.run([sys.executable, "-m", "factblock", "track-record", d + "/one", "--as-of", "2026-03-01"], capture_output=True, text=True, cwd=ROOT, check=True).stdout
    assert "+1.2% over 069500\n" in out, out
assert cramer["record"] == {"before": 0, "sourced": 779, "writer": 0}, cramer["record"]   # backfilled from dated recordings

print("PASS track_record: latest verdict as of, open and overdue, hit rate, on record before vs a cited source vs the writer's word, who vouches for each before count, ids and speaker, baseline (always up, following the calls, over a named benchmark or SPY), CLI, scan hint, cramer 426/353")
