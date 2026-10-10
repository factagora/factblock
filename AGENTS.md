# Working in this repository

FactBlock is a file format (`SPEC.md`) and its reference library (`factblock/`). The spec comes first: a behaviour change is a SPEC change, then code, then a test.

## Setup and checks

```bash
uv sync --group dev
for t in tests/test_*.py; do uv run python "$t" || break; done   # every test is a script that prints PASS
```

No test framework: each `tests/test_*.py` asserts and prints one PASS line. A new behaviour gets one check in the closest test file, or a new file if it is a new surface. Make it fail without your change before you trust it.

## Rules

- Every MUST in `SPEC.md` has a check id in `factblock/validate.py`. Add both or neither.
- Reads never default `as_of`. A writer that is not a ledger declares `known_at` as a backfill batch (SPEC 6); `write_bundle` does it for rows without `attestation`.
- Blocks are append-only. Corrections are new rows (`SUPERSEDES`, resolutions), never edits.
- The Python reader and the DuckDB macros (`duckdb/factblock.sql`) must give the same answer; `tests/test_duckdb.py` compares them.
- No new runtime dependency beyond `pyarrow`. Model SDKs are optional extras.
- Add a line to `CHANGELOG.md` for anything a user would notice.
- Prose: plain, second person, no em dashes. Say what the code does, not what it will do.
- Commits are signed off (`git commit -s`, DCO). See `CONTRIBUTING.md`.

## Map

| Path | What |
|---|---|
| `factblock/scan.py` | as-of visibility and the certificate (SPEC 4.1, 4.2) |
| `factblock/recall.py` | recall and context: what an agent puts in its prompt |
| `factblock/why.py`, `resolve.py`, `leak.py` | SPEC 4.5, 4.4, and the hindsight check |
| `factblock/extract.py`, `profiles/claims/` | text to blocks through a model; the profile is three language-neutral files |
| `factblock/records.py` | rows (CSV/JSONL) to blocks and verdicts, no model; `write_bundle` in `bundle.py` declares batches and validates before writing |
| `factblock/timeline.py` | statements over time as of a day, optionally over a numeric series; Vega-Lite spec, no new dependency. `Chart` is what every chart shares (HTML, MCP tool result, files) |
| `factblock/graph.py` | what one statement rests on and what came of it (the why() walk) as a chart; rows in a graph renderer's field names |
| `factblock/embed.py` | meaning for recall: `embedder()` for the optional model extras, statement vectors cached beside the bundle (an index, not part of it) |
| `factblock/sync.py` | folder to store, both ways (SPEC 6.1) |
| `factblock/adapters/` | Graphiti, Fact Check Tools |
| `samples/`, `examples/` | data the tests read; regenerate rather than hand-edit `samples/cramer` |
