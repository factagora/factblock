# Changelog

## 1.0-draft.1 (2026-10-04)

First public draft of the format and the reference library.

- Five invariants (three clocks, attested knowledge time, append-only, typed edges, declared facts) with one validator check id each.
- Logical model: node, edge, resolution, declarations (facts, backfill batches, edge types, embedding model).
- JSONL and Parquet profiles; Parquet files sorted by `known_at`, unknown fields kept in `extra`.
- Read semantics: as-of with certificate, `valid_at` defaulting to `as_of`, supersession, `resolve` by declared policy, expansion.
- Readers: the Python library (`scan`, `validate`, `resolve`, `write_parquet`) and the DuckDB macro pack.
- Writers: the tckg ledger (`GET /v1/export`) and the Graphiti adapter.

### Added (2026-10-05)
- `factblock extract`: text in, a batch of blocks out, through a model you choose (`gemini`, `openai`, or `fake` for offline runs). The claims profile lives in `factblock/profiles/claims/` as three files (instructions, output schema, edge types) so other languages run the same extraction. Every extract declares one backfill batch (SPEC 6: a non-ledger writer never invents `known_at`).
- `write_bundle(result, out, append=True)` in `factblock.bundle`: a folder grows one batch at a time and stays valid; entities are reused across batches.
- README rewritten as the project's front door: agent memory for decisions.
- `factblock why <bundle> <node_id> --as-of T [--valid-at T] [--depth N]` and `factblock.why()`: the chain behind one block on files, mirroring tckg's `why`. Both directions over causal, argumentative and temporal edges, a role at every hop, `not_yet` or `absent` when the root is not visible yet (SPEC 4.5).
- `factblock leak <bundle> <questions.jsonl>` and `factblock.leak()`: for a question set with `asked_at` and the block ids each answer rests on, which answers depend on blocks learned after the question was asked (`known_later`) or not in force then (`not_in_force`), per question and as a rate. Exit code 1 on any leak. Sample set: `samples/rates-questions.jsonl`.
- `factblock sync <bundle> <url> --space S [--token T] [--as-of T] [--push-only | --pull-only]` and `factblock.sync(bundle, store)`: a folder and a store, both ways, by identity. Rows only the folder has go up under the folder's batches; rows only the store has come down with the store's `known_at`; a second run is a no-op; `--pull-only` into a new folder clones a space. `Store` is a two-method protocol (`pull`, `push`); `TckgStore` speaks tckg's HTTP API with no dependency beyond the standard library. SPEC 6.1 states the import rule (declare the bundle's batches, never adopt a row as learned now).
- `write_bundle` writes a `resolutions` table when given one and serialises datetimes.
- `factblock to-claimreview <bundle> --as-of T [--base-url U]` and `factblock.to_claimreview()`: the verdicts visible as of an instant as schema.org ClaimReview JSON-LD (SPEC 9.2). Latest verdict per block, ratings from the new recommended `outcome` vocabulary (SPEC 3.6), the rest under `factblock:` keys.
- SPEC 3.1 names the payload conventions `extract` already writes (`speaker`, `quote`, `source`); SPEC 3.6 adds the recommended verdict vocabulary and the evidence element shape; SPEC 9 becomes two projections (OKF, ClaimReview) with the reverse-direction rule for fact-check feeds.
- `samples/rates` gains a `resolutions` table: two verdicts and one re-resolution, ledger-stamped, so as-of reads hide verdicts learned later.
