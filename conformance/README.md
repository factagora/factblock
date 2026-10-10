# Conformance cases

The answers a FactBlock reader has to give, so a reader in another language or engine can check itself against the
same files. `cases.jsonl` has one case per line:

| Field | Meaning |
|---|---|
| `bundle` | a JSONL bundle in this repository |
| `as_of`, `valid_at` | the read (a date means the end of that day, SPEC 4.1; `valid_at` null means `as_of`) |
| `nodes` | every visible block as `[id, superseded_by]`, sorted (SPEC 4.1, 4.3) |
| `verdicts` | the latest visible verdict on each block, `{target_id: outcome}` (SPEC 3.6) |
| `why` | what the case is about |

The cases cover a replacement announced before it takes effect, a statement learned after it was said, a block
replaced twice on the same day (`bundles/replaced-twice`), a re-resolved verdict, and `valid_at` apart from `as_of`.
`tests/test_conformance.py` runs the Python reader and the DuckDB macros (`duckdb/factblock.sql`) against them.
A new reader passes when it gives the same rows for every case.
