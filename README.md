# FactBlock: agent memory for decisions

**A temporal causal knowledge graph that remembers *when* and *why* for your AI.**

Your data is full of claims: facts, opinions, predictions, promises. FactBlock extracts them, keeps when they were said and when you learned them, links what caused what, and never overwrites what changed. Your agent recalls them as of any moment, so it decides on what was knowable then, not on hindsight.

```bash
pip install factblock

factblock extract transcript.txt --observed-at 2024-03-20 --speaker "Jim Cramer" --backfill -o brain/   # your model key
factblock scan brain/ --as-of 2024-05-01      # what was known that day, with a certificate of what was hidden
factblock why brain/ P3 --as-of 2024-08-01    # the causal chain behind a block
factblock resolve brain/ belief:fed:direction --as-of 2024-10-01
```

`brain/` is a folder of plain files. Commit it to git, query it with DuckDB, hand it to another agent, or [upload it to a hosted ledger](#same-files-hosted). Nothing here needs a server.

## What comes out

One transcript line, three blocks, two edges:

```
"The Fed will keep raising rates this year. That means bond yields keep climbing,
 so I'd stay out of long bonds."                         Jim Cramer, 2024-03-20

P1  prediction  The Fed keeps raising rates this year      asserted 2024-03-20
P2  prediction  Bond yields keep climbing
P3  prediction  Stay out of long bonds                     asset TLT, direction down

P1 --CAUSES--> P2 --CAUSES--> P3
```

Every block carries two clocks: **asserted_at**, when it was said (`--observed-at`), and **known_at**, when your system learned it. By default that is now, so a 2024 transcript extracted today is hidden from a 2024 read; `--backfill` declares it known when it was said, which is what you want for material from the past. Every edge carries a type with a family (causal, argumentative, temporal) and the speaker's own confidence. Nothing is a chunk, nothing is a bare triple; the unit is a dated statement someone made.

## When

Memory that cannot answer "what did I know on that date" leaks the future into every evaluation and every backtest. FactBlock reads are always **as of** an instant:

```python
import factblock
r = factblock.scan("brain/", as_of="2024-05-01")
r.nodes                 # pyarrow.Table: only blocks known by 2024-05-01
r.certificate           # {'as_of': ..., 'masked': {'node': 4, 'edge': 2}, 'backfill': {'batches': 1, 'rows': 3}}
```

The certificate says how many rows were hidden because they were learned later, and which rows were backfilled from the past under a declared batch. An answer with masking is a correct answer for that instant, and it says so.

A statement that gets corrected or reversed is not overwritten. The new block points at the old one with `SUPERSEDES`, both keep their intervals, and a read as of a date in between still sees the old one. That is how "when did they change their mind" stays answerable.

## Why

Edges are the speaker's reasoning, not co-occurrence: `CAUSES`, `CONTRIBUTING_FACTOR`, `TRIGGERS`, `PREVENTS`, `SUPPORTS`, `CONTRADICTS`, `CONCURRENT_SIGNAL`, `SUPERSEDES`. `why` walks them from a block to the given depth, as of an instant, and names the role at every hop (`cause`, `effect`, `successor`, `contradiction`), so the chain never includes a reason that was not yet known.

Declared facts make conflicts explicit. Declare `belief:fed:direction` with a policy (`latest_valid`, `latest_observed`, `source_priority`, `strict`) and `resolve` returns one value or the reason there is none: `no_data`, `not_yet`, `no_value_at`, `unresolved_conflict`. It never guesses.

## Claims it is good at

| Kind | Example | What you can ask that other memories cannot |
|---|---|---|
| **Prediction** | "Yields keep climbing this year" (podcast, 2024-03-20) | What did this person believe on 2024-03-20? Did it come true? When did they say the opposite? |
| **Stance** | CEO: "No price increase this year" (Jan), "An increase is unavoidable" (Jul) | How did the company's position move? What did we know in May? |
| **Fact that gets corrected** | "Q2 revenue was $4.1B", restated to $3.9B six weeks later | `resolve` as of August gives $4.1B, as of October $3.9B, as of July `no_data` |
| **Commitment** | Sales: "We ship SSO by end of Q3" (to customer A) | Which promises to A are past due and unresolved? Recall them before the support agent answers |
| **Your AI's own assertions** | Assistant: "Your plan includes 10 seats" (to user B) | Which of last month's assertions are now false? Where did each one come from? |

The common thread: a claim has a speaker, a time, a reason, and a later verdict. RAG keeps chunks, entity graphs keep triples, chat memories keep summaries. None of them keep that.

## Use it with your AI

**Recall as context.** `scan` returns Arrow tables; turn the visible blocks into the context your agent reads, with `as_of` set to the decision time (now, or a past instant for a backtest).

**Analytics.** `to-parquet` writes the Parquet profile. DuckDB reads it with no Python through [`duckdb/factblock.sql`](./duckdb/factblock.sql): `factblock_nodes(bundle, as_of)`, `factblock_edges`, `factblock_certificate`. Spark and Databricks read the same files.

**From an existing graph.** [`factblock/adapters/graphiti.py`](./factblock/adapters/graphiti.py) turns a Graphiti graph into a bundle; the store's own timestamps become declared backfill batches, because a store that stamped time itself is a witness.

**Check your evals.** `leak` takes a question set with dates and reports how many answers depend on blocks learned after the question's date. If your memory benchmark never reports this number, it is measuring hindsight.

## Same files, hosted

A folder is one writer's memory. [factagora.ai](https://factagora.ai) is where a `brain/` meets other people's. Upload it and it comes back with **more rows, never changed rows**: verdicts on predictions whose horizon has passed (mechanical ones from prices and published figures, judgment calls from the community, each with evidence), links to what other people claimed about the same thing (`SUPPORTS`, `CONTRADICTS`), entities resolved across worldviews. Every added row carries its own `known_at`, stamped by the server rather than by you, so a verdict is as replayable as the claim it judges: as of last June, the prediction was still open.

It also gives what a folder cannot: one ledger shared by many agents and users, natural-language writes at scale, and an MCP address per worldview, so a user plugs one into Claude or Cursor and reaches nothing else. Browse public worldviews there, or ask one a question as of a date. `GET /v1/export` hands the folder back at any instant. The format is the contract; you can leave with your files.

The same ledger runs closed for companies at [app.factagora.com](https://app.factagora.com): your support logs, your sales promises, your own assistant's assertions, as claims with verdicts, inside your tenant.

## The format

[`SPEC.md`](./SPEC.md) is short. Five invariants (present, attested, unique, typed, declared), a JSONL profile and a Parquet profile, read semantics, and the conformance checks `validate` runs (eleven of them). Projections to OKF and ClaimReview are described so a bundle can feed systems that speak those.

Format, not platform. Apache-2.0. tckg is one writer of this format; nothing here requires it.

## Status

`1.0-draft.1`. Works today: `extract` (providers `gemini`, `openai`, and `fake` for offline runs; the claims profile is three files under [`factblock/profiles/claims`](./factblock/profiles/claims) that any language can run), `validate`, `scan`, `why`, `resolve`, `to-parquet`, the DuckDB macros, the Graphiti adapter, and the tckg export. Extraction quality on real transcripts is being measured separately; the rules are the ones a dated-claims pipeline has run on hundreds of videos. Next, in this order: `leak`, `sync` with the hosted ledger, and the ClaimReview projection. The format reaches 1.0.0 when a reader or writer maintained outside this repository exists; until then minor versions may change fields and the manifest's `factblock_version` says which one a bundle speaks.

```bash
uv sync --extra gemini                                 # or --extra openai; the fake provider needs nothing
export GEMINI_API_KEY=...                              # or GOOGLE_GENAI_USE_VERTEXAI=1 GOOGLE_CLOUD_PROJECT=... for Vertex
echo "The Fed will keep raising rates this year. That means bond yields keep climbing." \
  | uv run python -m factblock extract - --observed-at 2024-03-20 --speaker "Jim Cramer" --backfill -o brain/
uv run python -m factblock scan brain/ --as-of 2024-05-01
```

```bash
uv sync
uv run python -m factblock validate samples/rates
uv run python -m factblock scan samples/rates --as-of 2024-08-01
uv run python -m factblock why samples/rates c3 --as-of 2024-10-01
uv run python -m factblock resolve samples/rates belief:fed:direction --as-of 2024-10-01
uv run python tests/test_rates.py && uv run python tests/test_why.py && uv run python tests/test_graphiti_adapter.py && uv run python tests/test_duckdb.py
```
