# FactBlock

**An open table format for knowledge that changes over time.**

Three clocks on every block (said, holds, known), typed causal edges, attested knowledge time, and declared rules for choosing between conflicting values. A reader can answer "what did we know at T, and why did we change our mind" from the files alone, and prove it did not peek.

- [`SPEC.md`](./SPEC.md): the format. Five invariants, logical model, JSONL and Parquet profiles, read semantics, conformance.
- [`factblock/`](./factblock): the Python reference library. `scan(bundle, as_of)` returns Arrow tables and a certificate; `validate` checks a bundle; `resolve` picks one value for a declared fact by its policy; `write_parquet` converts to the Parquet profile. Query the result with DuckDB, Spark, or anything that reads Arrow.
- [`factblock/adapters/graphiti.py`](./factblock/adapters/graphiti.py): the second writer. A Graphiti graph (its own objects, any backend) becomes a bundle; Graphiti's `created_at` is attested as backfill batches because the store stamped it itself.
- [`duckdb/factblock.sql`](./duckdb/factblock.sql): the format in DuckDB with no Python. Table macros `factblock_nodes(bundle, as_of)`, `factblock_edges`, `factblock_certificate` over a Parquet bundle, same rules as `scan`. One file to `-init`, no extension to install.
- [`samples/`](./samples): small bundles that exercise the invariants.

Format, not platform. Apache-2.0 (the LICENSE file lands when this folder goes public). tckg (the rest of this repository) is one ledger that writes this format; it is not required to read it.
This folder is self-contained so it can move to its own repository when the format goes public.

```bash
cd format && uv sync
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
