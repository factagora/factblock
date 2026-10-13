# Scale baseline: Parquet row groups

`run.py` builds a synthetic bundle (N claims said over 2000 to 2025, each learned at the end of its day under one
backfill batch per day, 3% replaced through `SUPERSEDES`, 5% restated), writes it in two Parquet layouts, and times
the DuckDB macros (`duckdb/factblock.sql`) at three instants. Every answer (visible nodes, replaced nodes, masked
count) is checked against `factblock.scan` before a time is kept. No data is downloaded or committed.

```bash
uv sync --group dev
uv run python bench/scale/run.py 100000      # about 15 s
uv run python bench/scale/run.py 1000000     # about 3 min
```

| layout | what wrote it |
|---|---|
| one row group | `write_parquet` before 1.0.0a17: pyarrow's default row group size, so up to 1M rows sit in one group |
| bounded | `write_parquet` now: at most 65,536 rows per group, in `known_at` order (SPEC 5.3) |

## Result

Seconds, best of three, on a 4-core VM with DuckDB 1.5.6 and pyarrow 25.0.1. `nodes` is
`count(*), count(superseded_by) FROM factblock_nodes(...)`, `certificate` is `factblock_certificate(...)`.

| N nodes | layout | row groups | 2010-06-30 nodes / certificate | 2024-01-31 | 2025-12-31 |
|---|---|---|---|---|---|
| 100,000 | one row group | 1 | 0.051 / 0.056 | 0.094 / 0.120 | 0.083 / 0.096 |
| 100,000 | bounded | 2 | 0.039 / 0.060 | 0.053 / 0.067 | 0.053 / 0.068 |
| 1,000,000 | one row group | 1 | 0.360 / 0.387 | 0.869 / 0.860 | 0.942 / 0.857 |
| 1,000,000 | bounded | 16 | 0.126 / 0.166 | 0.301 / 0.318 | 0.319 / 0.324 |

At 1M nodes the bounded layout reads about 3 times faster; at 100k, with two groups, about 1.5 times. Most of the
gain is DuckDB reading groups in parallel, which one group per file prevents. The answers are the same in both
layouts and in `scan`. The bounded file is about 10% larger (49.6 MB against 44.3 MB at 1M), because each group
starts its own dictionaries.

What this does not measure: the Python path (`Bundle`, `scan`, `write_bundle`) loads the whole bundle into memory,
and appending costs time in proportion to the bundle, not to the new rows. Measure those before you plan for tens of
millions of rows.
