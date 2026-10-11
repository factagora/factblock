# <img src="https://raw.githubusercontent.com/factagora/factblock/main/.github/logo.svg" alt="" height="40" align="top"> FactBlock: an open format for claims and their history

[![test](https://github.com/factagora/factblock/actions/workflows/test.yml/badge.svg)](https://github.com/factagora/factblock/actions/workflows/test.yml) [![PyPI](https://img.shields.io/pypi/v/factblock)](https://pypi.org/project/factblock/) [![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](https://github.com/factagora/factblock/blob/main/LICENSE)

**Build agent memory that tracks claims, evidence and changes, and lets you query what was known at any point in time.**

Represent temporal causal knowledge graphs in portable files, reusable across AI agents, analytics, and visualizations.

"The Team plan includes 10 seats." "We ship SSO in Q3." Who said it, when, on what basis, and did it change? FactBlock keeps that, so you do not build it.

It is files in a folder; [factagora.ai](https://factagora.ai) hosts the same files when you want to share them ([below](#same-files-hosted)).

![FactBlock in 40 seconds: reads as of a date, a causal chain, a claim replaced not overwritten, a verdict that arrives later, and the hindsight leak without a clock. Real data from samples/cramer and samples/rates.](https://raw.githubusercontent.com/factagora/factblock/main/samples/demo.gif)

```bash
pip install --pre factblock
factblock sample --policies irs/                                 # the IRS business mileage rate, 2022 to 2026, as CSV
factblock import irs/mileage.csv --backfill -o brain/
factblock import irs/mileage-2026-07.csv --backfill -o brain/    # 76 cents from July 1, announced July 13
factblock recall brain/ "mileage rate" --as-of 2026-07-10 --limit 1   # asked July 10: 72.5 (76 not announced yet)
factblock recall brain/ "mileage rate" --as-of 2026-07-20 --limit 2   # asked July 20: 76, and 72.5 marked replaced
```

```
irs-2026-01  claim       2025-12-29  The IRS business standard mileage rate is 72.5 cents per mile.
1 of 6 matching   as of 2026-07-10  hidden: 1 node, 1 edge

irs-2026-07  claim       2026-07-13  The IRS business standard mileage rate is 76 cents per mile.
irs-2026-01  claim       2025-12-29  The IRS business standard mileage rate is 72.5 cents per mile.
                           replaced 2026-07-01 by irs-2026-07: The IRS business standard mileage rate is 76 cents per mile.
2 of 7 matching   as of 2026-07-20  hidden: nothing
```

## In force from one day, announced on another

A trip on July 5, 2026: the IRS raised the rate to 76 cents from July 1 but announced it on July 13. The day of the trip and the day you ask are two clocks, and a date filter has one. `valid_at` is the trip, `as_of` the asking:

```python
import factblock
factblock.context("brain/", "mileage rate", as_of="2026-07-20", valid_at="2026-07-05", limit=2)
# - 2026-07-13: The IRS business standard mileage rate is 76 cents per mile. (in force from 2026-07-01; source: https://www.irs.gov/irb/2026-29_irb)
# - 2025-12-29: The IRS business standard mileage rate is 72.5 cents per mile. (in force from 2026-01-01; source: https://www.irs.gov/newsroom/irs-sets-2026-business-standard-mileage-rate-at-725-cents-per-mile-up-25-cents)
#   replaced 2026-07-01 by: The IRS business standard mileage rate is 76 cents per mile. (announced 2026-07-13)
```

Asked on July 10 with the same `valid_at` and `limit=1`, you get 72.5 cents and nothing replacing it. Every rate links to the IRS release it came from.

[`examples/support-agent`](https://github.com/factagora/factblock/tree/main/examples/support-agent) asks five support questions of a made-up company on the day they were asked (a price announced before it takes effect, a policy memo that arrived late, a promise and whether it was kept): a date filter puts a stale answer in the prompt on all five, FactBlock on none.

## Judged later, counted honestly

```bash
git clone https://github.com/factagora/factblock && cd factblock   # this sample is in the repository, not the package
```

```
$ factblock track-record samples/cramer --as-of 2026-10-01
      judged    right    wrong    mixed     open  overdue      hit
all      779      426      353        0      629       46      55%
on record before it was resolved: 0 of 779; 779 written later from a cited source (checkable)
baseline (779 calls with a return): saying up every time would hit 54%; following the calls made +5.2% a call, +1.4% over SPY
```

Two years of a TV commentator's market calls ([`samples/cramer`](https://github.com/factagora/factblock/tree/main/samples/cramer)): right about as often as saying "up" every time, yet +1.4% a call over the market ([`examples/analysis`](https://github.com/factagora/factblock/tree/main/examples/analysis)).

## Your own rows

Most memory starts as rows, not prose: a pricing table, a policy log, a CRM export. `import` takes them as they are, no model, and every date comes from your columns.

```
id,said_at,effective_from,known_at,text,replaces
p1,2026-01-10,,,The Team plan costs $30 per user per month.,
p2,2026-02-20,2026-03-15,,The Team plan costs $36 per user per month.,p1
```

`factblock import plans.csv --backfill -o kb/` writes them. `--backfill` reads a row without `known_at` as known when it was said; without it, as known today, so a read of an earlier day does not see it. Your own column names: `--map Claim=text,Date=said_at`.

`said_at` (or `asserted_at`) is when it was said, `effective_from` (or `valid_from`, default `said_at`) when it takes effect, `known_at` when you learned it, `replaces` the id it supersedes. A row with `target`, `outcome` and `decided_at` is a verdict. Any other column goes into the payload. In Python, any dicts with the format's own names will do:

```python
factblock.write_bundle({"nodes": [{"id": "r1", "kind": "claim", "statement": "Annual plans refund within 30 days.",
                                   "asserted_at": "2026-01-10", "known_at": "2026-01-10"}]}, "brain/", append=True)
```

`write_bundle` fills the manifest, declares one batch per `known_at`, and validates the whole folder before it writes; a bundle that would fail `validate` raises and is not written.

Prose instead of rows: `factblock extract notes.txt --observed-at 2024-03-20 --backfill -o brain/` through your model key (`--provider gemini` with `GEMINI_API_KEY` after `pip install --pre 'factblock[gemini]'`, or `openai`), or `--provider fake` to see the files without a model.

## For coding agents

The whole API in one block. It runs as is; `tests/test_readme_agents.py` keeps it that way.

```bash
pip install --pre factblock
factblock sample --policies irs/
factblock import irs/mileage.csv --backfill -o brain/
factblock import irs/mileage-2026-07.csv --backfill -o brain/
```

```python
import factblock
print(factblock.context("brain/", "mileage rate", as_of="2026-07-20", limit=2))   # prompt lines, as known that day
r = factblock.recall("brain/", "mileage rate", as_of="2026-07-20", limit=2)       # the same, as dicts
old = r["items"][1]
print(old["statement"], "->", old["superseded_by"]["statement"])                  # what replaced it
```

That string goes into your agent's prompt. The old rate is still there, marked as replaced. `factblock.recall(...)` returns the same blocks as dicts with a certificate, and `factblock.scan(...)` returns everything visible as Arrow tables. Add `--json` to any read on the command line for the machine form.

Words are matched as written. To match by meaning too, pass `embed=factblock.embedder("gemini")` (or `"openai"`, or your own function) to `recall`, `context` or `timeline`, or `--embed gemini` on the command line: "price" then finds a block that says "costs". The vectors are an index cached in `brain/.factblock-cache/`, not part of the bundle.

Three rules: every read takes `as_of` (no default, [SPEC 4](https://github.com/factagora/factblock/blob/main/SPEC.md#4-read-semantics)); a change is a new block plus `SUPERSEDES`, never an edit; `known_at` is when you learned a row: give it honestly (default now; `--backfill` means when it was said) and let `import`, `extract` or `write_bundle` declare the batch that attests it. Claude Code users can copy [`.claude/skills/factblock`](https://github.com/factagora/factblock/tree/main/.claude/skills/factblock) into their project; other agents read [`llms.txt`](https://github.com/factagora/factblock/blob/main/llms.txt).

| If you know | In FactBlock |
|---|---|
| Mem0 `m.add(messages, user_id=...)` | `factblock import` for rows, `factblock extract` for prose; in Python `from_records(rows)` or `extract(text, observed_at=...)`, then `write_bundle(..., append=True)`; the user is a `space` |
| Mem0 `m.search(query, user_id=...)` | `recall(bundle, query, as_of=...)` or `context(...)` for the prompt |
| Graphiti edge `valid_at` / `invalid_at` | `valid_from` / `valid_to` on the block, plus `known_at`: when you learned it |
| Graphiti `expired_at` (an edge closed later) | the old block stays; a new block `SUPERSEDES` it, known from that moment |
| A vector store with a date filter | `recall(as_of=..., embed=...)` matches by meaning too, and also hides what was learned later, keeps what was replaced (marked), and attaches verdicts. Vectors are an index cached beside the bundle (`.factblock-cache/`), not part of it |

## Charts

`factblock timeline brain/ --as-of 2026-10-10 -o mileage.html` draws the history from the same files.

![The IRS business mileage rate from 2022 to 2026, each rate replaced by the next](https://raw.githubusercontent.com/factagora/factblock/main/examples/analysis/img/irs-mileage-timeline.png)

Over a numeric series, inside a chat answer (MCP Apps), and what one statement rests on: [`docs/timelines.md`](https://github.com/factagora/factblock/blob/main/docs/timelines.md).

## Guides and examples

- [Your RAG answers with a rate that changed](https://github.com/factagora/factblock/blob/main/docs/guides/stale-policy-in-rag.md)
- [Show what an AI answer rested on, and what changed since](https://github.com/factagora/factblock/blob/main/docs/guides/answer-evidence-history.md)
- [Evaluate an agent only on what was known at the time](https://github.com/factagora/factblock/blob/main/docs/guides/evaluate-as-of.md): `leak` checks an eval set's evidence against each question's date. On [StreamingQA](https://github.com/factagora/factblock/tree/main/bench/streamingqa), a recall that ignores time cites a block learned after the question for **79.7% of questions**.
- [`examples/promises`](https://github.com/factagora/factblock/tree/main/examples/promises): sales promises from one CSV; open, past due, broken, kept as of any date.
- [`examples/analysis`](https://github.com/factagora/factblock/tree/main/examples/analysis): DuckDB and Jupyter over `samples/cramer`.
- DuckDB without Python: `to-parquet`, then [`duckdb/factblock.sql`](https://github.com/factagora/factblock/blob/main/duckdb/factblock.sql) (`factblock_nodes(bundle, as_of)`, `factblock_edges`, `factblock_certificate`). Spark and Databricks read the same files.
- Standards: `to-claimreview` (schema.org ClaimReview), `to-okf` (Open Knowledge Format), `from-factcheck` (Google Fact Check Tools). None of them is the storage format; they are doors.
- From an existing graph: [`factblock/adapters/graphiti.py`](https://github.com/factagora/factblock/blob/main/factblock/adapters/graphiti.py) turns a Graphiti graph into a bundle, its timestamps as declared backfill batches.

The three guides run as written on the IRS data above, with expected output and what they do not do.

## Same files, hosted

A folder is one writer's memory. [factagora.ai](https://factagora.ai) is where a `brain/` meets other people's. Upload it and it comes back with **more rows, never changed rows**: verdicts on predictions whose horizon has passed (mechanical ones from prices and published figures, judgment calls from the community, each with evidence), links to what other people claimed about the same thing (`SUPPORTS`, `CONTRADICTS`), entities resolved across worldviews. Every added row carries its own `known_at`, stamped by the server rather than by you, so a verdict is as replayable as the claim it judges: as of last June, the prediction was still open. One ledger is shared by many agents and users, with an MCP address per worldview; `GET /v1/export` hands the folder back at any instant, so you can leave with your files.

`factblock sync brain/ <url> --space <space>` moves rows both ways by identity: what only the folder has goes up, what only the ledger has comes down, nothing is changed in place. A row's `known_at` travels as the batch that attests it, so the ledger learns a 2024 transcript as known in 2024, not today, and the folder learns a verdict at the instant the ledger stamped it. Run it again and it is a no-op. `--pull-only` into a folder that does not exist yet clones a space. The token is `$TCKG_TOKEN` or `--token`. Another store is two methods: see [CONTRIBUTING.md](https://github.com/factagora/factblock/blob/main/CONTRIBUTING.md).

The same ledger runs closed for companies at [app.factagora.com](https://app.factagora.com): your support logs, your sales promises, your own assistant's assertions, as claims with verdicts, inside your tenant.

## The format and status

[`SPEC.md`](https://github.com/factagora/factblock/blob/main/SPEC.md) is short: six invariants, a JSONL and a Parquet profile, read semantics (what a read hides and the certificate that says so, section 4), edge types and their families (3.3), declared facts and `resolve` (3.7), and the thirteen checks `validate` runs. Nothing is a chunk, nothing is a bare triple; the unit is a dated statement someone made. A bundle is a folder of plain files: commit it to git, query it with DuckDB, hand it to another agent. Nothing here needs a server.

Format, not platform. Apache-2.0. tckg is one writer of this format; nothing here requires it. Contributions are welcome under the DCO: see [CONTRIBUTING.md](https://github.com/factagora/factblock/blob/main/CONTRIBUTING.md).

An alpha on PyPI (`pip install --pre factblock`), format `1.0-draft.1`. Extraction quality on real transcripts is being measured separately. The format reaches 1.0.0 when a reader or writer maintained outside this repository exists; until then minor versions may change fields and the manifest's `factblock_version` says which one a bundle speaks.
