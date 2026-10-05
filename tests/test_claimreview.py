"""The one check that fails if the ClaimReview projection breaks: verdicts come out as of an instant,
the latest verdict per block stands, outcomes map to ratings, and what ClaimReview cannot say rides
under factblock: keys. Run: uv run python tests/test_claimreview.py"""
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import factblock  # noqa: E402

RATES = pathlib.Path(__file__).resolve().parents[1] / "samples" / "rates"
by = lambda d: {r["factblock:id"]: r for r in d["@graph"]}  # noqa: E731

octo = factblock.to_claimreview(RATES, "2024-10-01", base_url="https://example.org/blocks")
assert octo["@context"] == "https://schema.org" and set(by(octo)) == {"c1", "c3"}, by(octo).keys()
c1 = by(octo)["c1"]
assert c1["@type"] == "ClaimReview" and c1["claimReviewed"] == "The Fed raises interest rates"
assert c1["reviewRating"] == {"@type": "Rating", "alternateName": "True", "ratingValue": 5, "bestRating": 5, "worstRating": 1}
assert c1["datePublished"] == "2024-05-01" and c1["itemReviewed"]["datePublished"] == "2024-03-20"
assert c1["itemReviewed"]["author"] == {"@type": "Person", "name": "analyst-1"} and c1["author"] == {"@type": "Organization", "name": "tckg-resolver"}
assert c1["url"] == "https://example.org/blocks/c1" and c1["factblock:known_at"].startswith("2024-05-02")
assert by(octo)["c3"]["reviewRating"]["ratingValue"] == 4
assert octo["factblock:certificate"]["masked"] == {"resolution": 1}     # the December re-resolution is not known yet

later = by(factblock.to_claimreview(RATES, "2025-01-01"))
assert later["c1"]["reviewRating"]["alternateName"] == "False" and later["c1"]["author"]["@type"] == "Person"   # latest verdict wins
assert "url" not in later["c1"]
assert factblock.to_claimreview(RATES, "2024-04-01")["@graph"] == []

out = subprocess.run([sys.executable, "-m", "factblock", "to-claimreview", str(RATES), "--as-of", "2024-10-01"], capture_output=True, text=True, check=True).stdout
assert len(json.loads(out)["@graph"]) == 2
print("PASS claimreview: 2 reviews as of October, ratings, authors, latest verdict in January, none in April, CLI")
