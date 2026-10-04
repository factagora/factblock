# FactBlock

**An open table format for knowledge that changes over time.**

Three clocks on every block (said, holds, known), typed causal edges, attested knowledge time, and declared rules for choosing between conflicting values. A reader can answer "what did we know at T, and why did we change our mind" from the files alone, and prove it did not peek.

- [`SPEC.md`](./SPEC.md): the format. Five invariants, logical model, JSONL and Parquet profiles, read semantics, conformance.
- [`factblock/`](./factblock): the Python reference library. `scan(bundle, as_of)` returns Arrow tables and a certificate; `validate` checks a bundle; `resolve` picks one value for a declared fact by its policy; `write_parquet` converts to the Parquet profile. Query the result with DuckDB, Spark, or anything that reads Arrow.
- [`duckdb/factblock.sql`](./duckdb/factblock.sql): the format in DuckDB with no Python. Table macros `factblock_nodes(bundle, as_of)`, `factblock_edges`, `factblock_certificate` over a Parquet bundle, same rules as `scan`. One file to `-init`, no extension to install.
- [`factblock/adapters/graphiti.py`](./factblock/adapters/graphiti.py): the second writer. A Graphiti graph (its own objects, any backend) becomes a bundle; Graphiti's `created_at` is attested as backfill batches because the store stamped it itself.
- [`samples/`](./samples): small bundles that exercise the invariants.

Format, not platform. Apache-2.0. [tckg](https://github.com/factagora/tckg) is one ledger that writes this format; nothing here requires it.

```bash
uv sync
uv run python -m factblock validate samples/rates
uv run python -m factblock scan samples/rates --as-of 2024-08-01
uv run python -m factblock resolve samples/rates belief:fed:direction --as-of 2024-10-01
uv run python -m factblock to-parquet samples/rates /tmp/rates-pq     # the Parquet profile; DuckDB or Spark read it directly
duckdb -init duckdb/factblock.sql -c "SELECT id, statement, superseded_by FROM factblock_nodes('/tmp/rates-pq', factblock_day('2024-10-01'))"
```

```python
import factblock, duckdb
r = factblock.scan("samples/rates", as_of="2024-08-01")
nodes, edges = r.nodes, r.edges                                 # pyarrow.Table, visible as of that instant
duckdb.sql("select id, statement, superseded_by from nodes")    # DuckDB reads Arrow tables by variable name
r.certificate   # {'as_of': ..., 'masked': {'node': 1, 'edge': 1}, 'backfill': {'batches': 2, 'rows': 5}}
```

## Status

`1.0-draft.1`. Two writers exist (the tckg ledger and the Graphiti adapter) and two readers (this library and the DuckDB macros). The format reaches 1.0.0 when a reader or writer maintained outside this repository exists. Until then every minor version may change fields; the manifest's `factblock_version` says which one a bundle speaks.

## Tests

```bash
uv run python tests/test_rates.py              # validator, scan at three instants, resolve, Parquet round trip
uv run python tests/test_graphiti_adapter.py   # the second writer
uv run python tests/test_duckdb.py             # the macros equal scan
```
