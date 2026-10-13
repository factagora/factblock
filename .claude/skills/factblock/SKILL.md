---
name: factblock
description: Agent memory read as of a point in time, with the factblock Python library (an open format for claims and their history). Use when an agent must answer from information that changes (prices, policies, corrected answers, promises, predictions), must not see the future in a backtest or replay, must say what was known when it answered, or must keep a track record of claims, predictions and commitments judged on outcomes. Typical requests include remember what the price was when the customer asked, read memory as of a date, no hindsight in a backtest, which of the assistant's answers are now wrong, keep corrections as history, temporal knowledge graph in files, track record of predictions, hit rate of promises.
---

# factblock

Install: `pip install --pre factblock` (alpha; `--pre` is required). Extraction with a model: `pip install --pre 'factblock[gemini]'` or `'factblock[openai]'`. Install anything else (duckdb, pandas) in a separate `pip install`: `--pre` applies to every package on the line and pulls their development builds too.

A **bundle** is a folder: `factblock.json` plus `nodes.jsonl`, `edges.jsonl`, `resolutions.jsonl`. Every function takes the folder path or a `factblock.Bundle`.

## Write

```bash
factblock import kb.csv -o brain/ --backfill                                        # rows in (CSV/JSONL), no model; --map Claim=text,Date=said_at for your column names
factblock extract notes.txt --observed-at 2026-03-14 -o brain/ --provider gemini   # text in, dated blocks out
factblock extract items.jsonl -o brain/ --provider gemini --backfill                # one {text, observed_at, speaker?, source?} per line
factblock sample brain/                                                             # a small bundle to try reads on
factblock sample --policies irs/                                                    # the IRS mileage rates as two CSVs: import irs/mileage.csv, then irs/mileage-2026-07.csv (both --backfill)
```

`--provider fake` needs no model (one block per sentence). `--backfill` means "known when it was said", for past material; without it the blocks are known now.

`import` columns: `id`, `statement` (or `text`), `asserted_at` (or `said_at`), `valid_from` (or `effective_from`, default `asserted_at`), `valid_to`, `known_at`, `kind`, `replaces` (`id;id`, writes `SUPERSEDES`); a row with `target`, `outcome`, `decided_at` is a verdict; other columns go to `payload`. Payload conventions (SPEC 3.1): `speaker`; `source` as `{url, title, published_at, id}` (`id`: the source's own document number); `asserted_at_precision` (`day`, `hour`, `minute`, `second`) when the source gave only a date or a time to the minute. A block or edge in the bundle may also carry a top-level `namespace`, where it came from (`bls.gov`), apart from the manifest `namespace` and `payload.source`: optional, null by default, never copied from the manifest, and its own column in Parquet and DuckDB. From Python: `factblock.write_bundle(factblock.from_records(rows), "brain/", append=True)`, or pass `{"nodes": [...], "edges": [...], "resolutions": [...]}` with the format's own field names. `write_bundle` declares batches and validates before writing; an invalid bundle raises `ValueError` and nothing is written.

Verdict, resolution: the same thing, a row in `resolutions.jsonl` (`outcome` is its value). `resolve` is different: one value for a declared `fact_key`.

## Read

```python
import factblock
ctx = factblock.context("brain/", "refund policy", as_of="2026-04-10")   # prompt lines, as known then
r = factblock.recall("brain/", "refund policy", as_of="2026-04-10")      # same, as dicts: items[i]["superseded_by"], ["verdict"], ["known_at"]
r = factblock.recall("brain/", "mileage rate", as_of="2026-07-10", valid_at="2026-07-05")   # as known on the filing day, in force on the trip day (default valid_at = as_of)
r = factblock.recall("brain/", "what does it cost", as_of="2026-04-10", embed=factblock.embedder("gemini"))   # by meaning too
w = factblock.why("brain/", r["items"][0]["id"], as_of="2026-04-10")     # causes, effects, replacements of one block
s = factblock.scan("brain/", as_of="2026-04-10")                         # everything visible, as Arrow tables (.nodes, .edges, .resolutions)
```

`recall` and `context` return every kind of statement (claims, predictions, your own kinds such as `commitment`) and leave out entities, factors, timeseries and episodes; `kinds=(...)` narrows it and `result["excluded"]` counts what was left out. Matching is keyword-based over the statement and payload text (a shared 4-letter stem counts), so query with the words the statements use; `""` lists everything. `verdict=` filters by the latest visible verdict: an outcome (`did_not` for a prediction, `broken` for a commitment), `"open"`, `"resolved"`, or `"overdue"` (past its deadline, no verdict). `fact_key=` (one key or a list) keeps only blocks carrying that declared key, so blocks that share the words but answer another question stay out. Items carry `due` (deadline ahead) or `ended` (passed), and `verdict`, `superseded_by`, `upcoming`, `basis_replaced` (a block it rests on by `DERIVED_FROM`, such as an import's `based_on` column, was replaced; one hop) when they apply; absent keys mean they do not. Announced changes not in force yet come back as `item["upcoming"]` (on the block they will replace) or in `result["upcoming"]`.

To record what an answer rested on, write the answer as a block and one `SUPPORTS` edge from each block it used; `why` follows `SUPPORTS` (and causal and temporal edges), not `DERIVED_FROM`. Later, `why("brain/", "answer-1", as_of="2026-07-20")` lists each relied-on block (`support`) and the block that replaced it (`successor`). Leave `valid_at` out there: the answer itself was not said yet on the trip day, so `valid_at="2026-07-05"` hides it.

```python
at = "2026-07-10T15:00:00Z"
factblock.write_bundle({"nodes": [{"id": "answer-1", "kind": "claim", "statement": "Reimburse the July 5 trip at 72.5 cents a mile.", "asserted_at": at, "known_at": at}],
                        "edges": [{"source_id": "irs-2026-01", "target_id": "answer-1", "edge_type": "SUPPORTS", "asserted_at": at, "known_at": at}]}, "brain/", append=True)
```

`as_of` accepts `'2026-04-10'` (the end of that day, UTC), an ISO timestamp, a `date` or a `datetime`. Dates are UTC days, on reads and writes alike (a date-only `said_at` or `known_at` is midnight UTC). For a local day pass the offset: `as_of='2026-04-10T23:59:59-07:00'` is the end of April 10 in California, `said_at` `2026-04-10T09:00:00+09:00` is 9am in Seoul. Every result carries a `certificate`: what the read hid because it was learned later (`masked`) or not in force (`not_in_force`).

## Show it over time

```python
t = factblock.timeline("brain/", as_of="2026-04-10", query="refund policy")   # one bar per statement: said until replaced, judged or due; group_by="speaker" groups rows
g = factblock.graph("brain/", "<block id>", as_of="2026-04-10")   # what it rests on above, what came of it below; depth=2 walks further
r = factblock.track_record("brain/", as_of="2026-04-10", by="speaker")   # right, wrong, open, overdue, hit_rate per group; r["record"]: on record before the verdict, or written later (from a cited source, or on the writer's word); r["total"]["baseline"] when verdicts carry a return: "up" every time, and what following the calls made; r["record_vouched_by"]: on whose word (a ledger, or a batch declared_by) each "before" rests
mine = factblock.track_record("brain/", as_of="2026-04-10", ids=[i["id"] for i in factblock.recall("brain/", "Nvidia", as_of="2026-04-10")["items"]])   # only calls like the one in front of you; speaker= for one speaker
t.with_series("prices.csv", "Price")                                          # over a numeric series (date, value CSV); values after as_of are dropped
t.save("out.html")                                                             # or .png/.svg with factblock[viz]; t.spec() is Vega-Lite, t.to_dict() the rows
```

## Rules

1. Every read takes `as_of`. There is no default; pass the moment the question was asked.
2. Never edit or delete a block. A change is a new block plus a `SUPERSEDES` edge from new to old; a verdict is a row in `resolutions.jsonl`. Old blocks come back marked `superseded_by`.
3. `known_at` is when you learned a row. Give it honestly (default now; `--backfill` = when it was said) and let `import`, `extract` or `write_bundle` declare the batch that attests it. Set `attestation.ledger` only for rows you stamp yourself the moment you first see them (a live collector, SPEC 6), with your own actor name, such as `process:my-collector`; readers trust that stamp as far as they trust the name. Past material, imports and copies always go through a declared batch.

## Check, convert, share

```bash
factblock validate brain/                    # 13 checks, all ok
factblock leak brain/ questions.jsonl        # answers that used blocks learned after the question (date-only asked_at = start of that day); --asked-key/--evidence-key for other field names
# each leaked citation has a reason: known_later (hindsight) or not_in_force (known, but not in force at the question's valid_at); known_later_questions counts hindsight only
factblock to-parquet brain/ brain-pq/        # DuckDB, Spark
factblock sync brain/ https://tckg.factagora.com --space user:me   # hosted ledger, both ways ($TCKG_TOKEN)
```

Spec: https://github.com/factagora/factblock/blob/main/SPEC.md
