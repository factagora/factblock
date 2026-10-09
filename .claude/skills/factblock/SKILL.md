---
name: factblock
description: Agent memory read as of a point in time with the factblock Python library. Use when an agent must answer from information that changes (prices, policies, corrected answers, promises, predictions), must not see the future in a backtest or replay, or must say what was known when it answered.
when_to_use: "remember what the price was when the customer asked", "read memory as of a date", "no hindsight in a backtest", "which of the assistant's answers are now wrong", "keep corrections as history", "temporal knowledge graph in files"
---

# factblock

Install: `pip install --pre factblock` (alpha; `--pre` is required). Extraction with a model: `pip install --pre 'factblock[gemini]'` or `'factblock[openai]'`.

A **bundle** is a folder: `factblock.json` plus `nodes.jsonl`, `edges.jsonl`, `resolutions.jsonl`. Every function takes the folder path or a `factblock.Bundle`.

## Write

```bash
factblock import kb.csv -o brain/ --backfill                                        # rows in (CSV/JSONL), no model
factblock extract notes.txt --observed-at 2026-03-14 -o brain/ --provider gemini   # text in, dated blocks out
factblock extract items.jsonl -o brain/ --provider gemini --backfill                # one {text, observed_at, speaker?, source?} per line
factblock sample brain/                                                             # a small bundle to try reads on
```

`--provider fake` needs no model (one block per sentence). `--backfill` means "known when it was said", for past material; without it the blocks are known now.

`import` columns: `id`, `statement` (or `text`), `asserted_at` (or `said_at`), `valid_from` (or `effective_from`, default `asserted_at`), `valid_to`, `known_at`, `kind`, `replaces` (`id;id`, writes `SUPERSEDES`); a row with `target`, `outcome`, `decided_at` is a verdict; other columns go to `payload`. From Python: `factblock.write_bundle(factblock.from_records(rows), "brain/", append=True)`, or pass `{"nodes": [...], "edges": [...], "resolutions": [...]}` with the format's own field names. `write_bundle` declares batches and validates before writing; an invalid bundle raises `ValueError` and nothing is written.

Verdict, resolution: the same thing, a row in `resolutions.jsonl` (`outcome` is its value). `resolve` is different: one value for a declared `fact_key`.

## Read

```python
import factblock
ctx = factblock.context("brain/", "refund policy", as_of="2026-04-10")   # prompt lines, as known then
r = factblock.recall("brain/", "refund policy", as_of="2026-04-10")      # same, as dicts: items[i]["superseded_by"], ["verdict"], ["known_at"]
w = factblock.why("brain/", r["items"][0]["id"], as_of="2026-04-10")     # causes, effects, replacements of one block
s = factblock.scan("brain/", as_of="2026-04-10")                         # everything visible, as Arrow tables (.nodes, .edges, .resolutions)
```

`recall` and `context` return every kind of statement (claims, predictions, your own kinds such as `commitment`) and leave out entities, factors, timeseries and episodes; `kinds=(...)` narrows it and `result["excluded"]` counts what was left out. Matching is keyword-based over the statement and payload text (a shared 4-letter stem counts), so query with the words the statements use; `""` lists everything. `verdict=` filters by the latest visible verdict: an outcome (`did_not` for a prediction, `broken` for a commitment), `"open"`, `"resolved"`, or `"overdue"` (past its deadline, no verdict). Items carry `due` (deadline ahead) or `ended` (passed), and `verdict`, `superseded_by`, `upcoming` when they apply; absent keys mean they do not. Announced changes not in force yet come back as `item["upcoming"]` (on the block they will replace) or in `result["upcoming"]`.

`as_of` accepts `'2026-04-10'` (the end of that day, UTC), an ISO timestamp, a `date` or a `datetime`. Every result carries a `certificate`: what the read hid because it was learned later (`masked`) or not in force (`not_in_force`).

## Show it over time

```python
t = factblock.timeline("brain/", as_of="2026-04-10", query="refund policy")   # one bar per statement: said until replaced, judged or due; group_by="speaker" groups rows
t.with_series("prices.csv", "Price")                                          # over a numeric series (date, value CSV); values after as_of are dropped
t.save("out.html")                                                             # or .png/.svg with factblock[viz]; t.spec() is Vega-Lite, t.to_dict() the rows
```

## Rules

1. Every read takes `as_of`. There is no default; pass the moment the question was asked.
2. Never edit or delete a block. A change is a new block plus a `SUPERSEDES` edge from new to old; a verdict is a row in `resolutions.jsonl`. Old blocks come back marked `superseded_by`.
3. `known_at` is when you learned a row. Give it honestly (default now; `--backfill` = when it was said) and let `import`, `extract` or `write_bundle` declare the batch that attests it. Never write `attestation.ledger` yourself; only a ledger stamps its own.

## Check, convert, share

```bash
factblock validate brain/                    # 11 checks, all ok
factblock leak brain/ questions.jsonl        # answers that used blocks learned after the question (date-only asked_at = start of that day)
factblock to-parquet brain/ brain-pq/        # DuckDB, Spark
factblock sync brain/ https://tckg.factagora.com --space user:me   # hosted ledger, both ways ($TCKG_TOKEN)
```

Spec: https://github.com/factagora/factblock/blob/main/SPEC.md
