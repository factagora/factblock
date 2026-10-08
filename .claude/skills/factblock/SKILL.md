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
factblock extract notes.txt --observed-at 2026-03-14 -o brain/ --provider gemini   # text in, dated blocks out
factblock extract items.jsonl -o brain/ --provider gemini --backfill                # one {text, observed_at, speaker?, source?} per line
factblock sample brain/                                                             # a small bundle to try reads on
```

`--provider fake` needs no model (one block per sentence). `--backfill` means "known when it was said", for past material; without it the blocks are known now.

## Read

```python
import factblock
ctx = factblock.context("brain/", "refund policy", as_of="2026-04-10")   # prompt lines, as known then
r = factblock.recall("brain/", "refund policy", as_of="2026-04-10")      # same, as dicts: items[i]["superseded_by"], ["verdict"], ["known_at"]
w = factblock.why("brain/", r["items"][0]["id"], as_of="2026-04-10")     # causes, effects, replacements of one block
s = factblock.scan("brain/", as_of="2026-04-10")                         # everything visible, as Arrow tables (.nodes, .edges, .resolutions)
```

`as_of` accepts `'2026-04-10'` (the end of that day, UTC), an ISO timestamp, a `date` or a `datetime`. Every result carries a `certificate`: what the read hid because it was learned later (`masked`) or not in force (`not_in_force`).

## Rules

1. Every read takes `as_of`. There is no default; pass the moment the question was asked.
2. Never edit or delete a block. A change is a new block plus a `SUPERSEDES` edge from new to old; a verdict is a row in `resolutions.jsonl`. Old blocks come back marked `superseded_by`.
3. Never set `known_at` yourself. `extract` and `write_bundle` declare a backfill batch; a ledger stamps its own.

## Check, convert, share

```bash
factblock validate brain/                    # 11 checks, all ok
factblock leak brain/ questions.jsonl        # answers that used blocks learned after the question
factblock to-parquet brain/ brain-pq/        # DuckDB, Spark
factblock sync brain/ https://tckg.factagora.com --space user:me   # hosted ledger, both ways ($TCKG_TOKEN)
```

Spec: https://github.com/factagora/factblock/blob/main/SPEC.md
