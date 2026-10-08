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
- `factblock to-okf <bundle> <out> --as-of T` and `factblock.to_okf()`: one OKF v0.2 concept document per visible node, relations as links with the relation in prose, `index.md` with the certificate, `log.md` in `known_at` order (SPEC 9.1). No YAML dependency: JSON is YAML.
- `factblock from-factcheck -o <bundle> (--query Q | --from-json FILE)` and `factblock.adapters.factcheck`: fact-checks in the Fact Check Tools API shape become claim nodes and verdict rows, each under a batch declared at its review date; `textualRating` is normalised to the recommended vocabulary where it fits and kept verbatim as `value`; re-import adds nothing. Live search needs `$FACTCHECK_API_KEY`.
- SPEC 3.5 adds the `org:<id>` actor shape for publishers and institutions.
- CLI: `factblock sample <dir>` copies the sample bundle (shipped in the wheel); `scan`, `why` and `resolve` print for people by default and take `--json`; every subcommand has help text and they are listed in the order you meet them. `extract` writes 8-character ids you can type.
- Repository: CONTRIBUTING (DCO), RELEASING, CODE_OF_CONDUCT, issue templates.
- `factblock recall <bundle> "<query>" --as-of T [--limit N] [--all-kinds]` and `factblock.recall()` / `factblock.context()`: the blocks about something as of an instant, ranked by query hits then recency, with the certificate. Keyword matching only; no embeddings yet.
- `samples/cramer`: a real bundle. Jim Cramer on CNBC, 2024-09 to 2026-09: 2,091 blocks under one backfill batch per recording, 1,169 typed links, 779 calls settled at their horizon as resolution rows. README's "What comes out" shows it. The reader test reads it at three instants.
- CLI exits quietly when its output pipe closes (`| head`).
- README: the logo in the title, `pip install --pre factblock` (the package is an alpha), and absolute links and images so the PyPI page renders them.
- `bench/streamingqa`: the hindsight number. StreamingQA's 36,378 dated questions as dated blocks; a time-ignorant top-5 recall leaks on 79.7% of questions (41.8% of picks), the as-of recall on none. `factblock.scan` now wraps a table-free `visible()` and `recall` keeps per-node word sets; a recall over 36,378 blocks takes under a second

### Fixed (2026-10-06, found migrating factagora.ai's 46,112 rows into tckg)
- `validate` accepted only `attestation.ledger`; SPEC I2 and 6 also allow a declared batch alone, which is what a non-ledger writer (an export script) produces. Both now pass, neither fails.
- `sync` compared edge and resolution instants as strings, so a ledger spelling `...57.89332+00:00` for a folder's `...57.893320+00:00` made a second run re-push 1,297 edges and pull them back into the folder as duplicates. Identity keys now compare instants, not spellings.

### Fixed (2026-10-06, from the table-format review)
- Certificate (SPEC 4.2): `masked` counts only blocks learned after `as_of`; blocks known but not in force at `valid_at` move to a new `not_in_force` key. The Python reader counted both as masked and the DuckDB macro only the first, so the same read gave two certificates (samples/rates with `valid_at`: 4 vs 0). `factblock_certificate` gains `not_in_force_nodes`/`not_in_force_edges`; the DuckDB test now compares under `valid_at` too.
- `why` (SPEC 4.5): the certificate covers the walk (hidden edges at the chain's nodes and the neighbours they lead to), not the bundle. A five-block cramer chain carried `masked: {node: 1790, ...}`; it now carries what that chain hid.
- Graphiti adapter: an invalidated fact no longer leaks hindsight. Graphiti closes facts in place; writing `valid_to = invalid_at` on a row known at `created_at` hid the fact from reads between `created_at` and `expired_at`, when the store still believed it. The original row stays open and a closed copy `<uuid>~closed`, known at `expired_at`, SUPERSEDES it.
- Parquet rows are sorted by UTC instant (Arrow `sort_by`), not by the text of the timestamp; mixed offsets were out of order.
- `write_bundle` writes rows first and the manifest last via `os.replace`, so a reader never sees a batch declared before its rows.
- SPEC 3.7 says what both readers and tckg already do: `latest_observed` ranks by `known_at`, ties are a conflict. SPEC 5.4: an Iceberg/Delta/DuckLake snapshot at T is not an as-of read (backfills after T, expiry); apply `WHERE known_at <= T` to the current snapshot.

### Added (2026-10-06)
- `factblock extract items.jsonl -o brain/`: one `{text, observed_at, speaker?, source?, known_at?}` per line, one batch per line, so a folder of dated transcripts or notes goes in with one command instead of a shell loop. `--observed-at`, `--speaker`, `--source-name` and `--known-at` become defaults that a line can override.

### Changed (2026-10-07)
- `recall` and `context` carry what happened to each block since, as far as it was known at `as_of`: `superseded_by` (the replacing block, from a visible SUPERSEDES row), `verdict` (the latest visible resolution), `source` and `known_at`. `context` prints them as indented lines and marks blocks learned a day or more after they were said. A correction or verdict learned after `as_of` stays hidden, so the same query reads differently at different instants.
- `examples/support-agent`: five dated support questions (announced price, a bot answer corrected, a promise and its outcome, a policy learned late, a retired API), each answered from a date-filtered memory and from `factblock.context()`. A context fails when it presents a stale statement as current or omits the verdict: date filter 0/5, FactBlock 5/5. Deterministic, no model. `tests/test_support_example.py`.
- `recall` keeps a block whose validity ended before `valid_at` when it has a verdict known by `as_of`, marked `ended`. A prediction or promise used to vanish from recall the moment its deadline passed, which is when its verdict arrives; on samples/cramer 17 settled calls came back.
