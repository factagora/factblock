"""The one check that fails if the OKF projection breaks: one document per visible node, frontmatter
the OKF way, supersession as links, the log in known_at order. Run: uv run python tests/test_okf.py"""
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import factblock  # noqa: E402

RATES = pathlib.Path(__file__).resolve().parents[1] / "samples" / "rates"
with tempfile.TemporaryDirectory() as d:
    out = factblock.to_okf(RATES, "2024-10-01", d)
    names = sorted(p.name for p in out.glob("*.md"))
    assert names == ["c1.md", "c2.md", "c3.md", "c4.md", "index.md", "log.md", "t1.md", "t2.md"], names
    c1 = (out / "c1.md").read_text()
    assert c1.startswith("---\ntype: \"claim\"\ntitle: \"The Fed raises interest rates\"\n"), c1[:120]
    assert 'resource: "factblock:sample:rates/c1"' in c1 and 'tags: ["macro"]' in c1 and '"by": "human:analyst-1"' in c1
    assert 'superseded_by: ["c4.md"]' in c1 and "- [c4](c4.md) supersedes this" in c1 and "- This causes [c2](c2.md)" in c1
    assert "## Verdicts" in c1 and "- true, decided 2024-05-01 by process:tckg-resolver" in c1 and "false" not in c1.split("## Verdicts")[1]
    assert 'supersedes: ["c1.md"]' in (out / "c4.md").read_text()
    assert "## Verdicts" not in (out / "c2.md").read_text()
    index = (out / "index.md").read_text()
    assert index.startswith('---\nokf_version: "0.2"\n') and "[The Fed raises interest rates](c1.md) (claim)" in index and '"masked": {"resolution": 1}' in index
    log = [l for l in (out / "log.md").read_text().splitlines() if l.startswith("- ")]
    assert log[0].startswith("- 2024-04-15") and log[-1].startswith("- 2024-10-01") and "verdict on [c3](c3.md): mostly_true" in log[-1], log
with tempfile.TemporaryDirectory() as d:
    may = factblock.to_okf(RATES, "2024-05-01", d)
    assert sorted(p.name for p in may.glob("*.md")) == ["c1.md", "c2.md", "index.md", "log.md"]
    assert "## Verdicts" not in (may / "c1.md").read_text()      # the May 2 verdict is not known on May 1
print("PASS okf: 6 documents as of October, frontmatter, supersession links, relations in prose, verdicts, log order, 2 in May")
