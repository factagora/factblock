# What a bundle can tell you that a table cannot

Two years of Jim Cramer's calls on CNBC ([`samples/cramer`](../../samples/cramer): 2,091 statements, 1,169 links he drew between them, 779 calls settled by the price move at their horizon), analysed in DuckDB. Each chart answers a question from something a plain table of statements does not keep. The same data then becomes a model's context, and every line the model cites leads back to the recording.

```bash
git clone https://github.com/factagora/factblock && cd factblock
pip install --pre factblock duckdb vl-convert-python jupyterlab
jupyter lab examples/analysis/analysis.ipynb
```

The [notebook](analysis.ipynb) is committed with its outputs, so you can read it on GitHub without running anything. In Jupyter the charts are interactive: hover for the statement and its FactBlock id, click to open the recording.

## 1. His record at the time was not his record today

![On 1 Jul 2025 his record read 46%. A backtest on today's data says 53% for that same day.](img/track_record.png)

Every verdict is a row with its own `known_at`: the day the horizon price settled. So the record replays as it stood on any day (blue). A table that keeps only the final outcome can only draw the orange line, which scores past days with verdicts that did not exist yet. On 1 July 2025 that is 108 verdicts from the future, and 46% becomes 53%. A backtest of anything that followed him would make the same mistake.

## 2. Changing his mind did not change his accuracy

![He reversed himself 108 times. Where both calls were settled, 10 reversals fixed a wrong call and 10 broke a right one.](img/reversals.png)

When he turned from "avoid Oklo" (February 2025) to "Oklo is a good investment" (June 2025), the new call does not overwrite the old one: it `SUPERSEDES` it, and both stay in the bundle with their own verdicts. That is what makes the question answerable at all. A store that updates in place keeps only the latest view.

## 3. Giving reasons did not make his calls better

![Giving a reason did not make him more accurate: 54% with a reason, 56% without.](img/reasons.png)

The reasons are the links he drew himself (`CAUSES`, `SUPPORTS`, ...), stored next to the calls and the verdicts, so this is one join. The links are **recorded, not verified**: a `CAUSES` edge says he said one thing causes another. Only the verdict is checked.

## Drill down to the statements

Every number above is made of blocks with ids and sources. Two drill-downs in the notebook show them: every call on the market (SPY) at the day it was said, up or down, coloured by what became of it; and one call ("The stock market is positioned to move higher", 21 March 2025) with the reasons he gave and the follow-up that did not come true.

<p><img src="img/stance.png" width="49%" alt="Every call on SPY, up or down, by outcome"> <img src="img/evidence.png" width="49%" alt="One call, its recorded reasons and the follow-up"></p>

## Then ask a model

The notebook asks "Is Cramer bullish on the stock market right now, and why?" as of 24 March 2025. `factblock.context(..., ids=True)` gives the model only what was known that day, one line per statement with its id. The model cites ids, and the notebook prints each cited statement with its quote and the link to the recording. Set `OPENAI_API_KEY` or `GEMINI_API_KEY` for a real answer; without one, the notebook shows the prompt the model would get.

The same call reads differently two weeks later. On 26 March, "the bulls hold the advantage heading into April" is an open call. On 10 April it has ended, settled as **did not** on 3 April. Nothing was edited in between: a verdict row became visible.

## How it is built

| Piece | What it does |
|---|---|
| [`views.py`](views.py) | The analysis. `track_record()`, `reversals()` and `reasons()` (the findings) and `stance()`, `evidence()` (the drill-downs) run SQL in DuckDB over the Parquet profile and the macro pack ([`duckdb/factblock.sql`](../../duckdb/factblock.sql)). Each returns `{"view", "title", "as_of", "rows", "spec"}`: the title is the finding, the rows carry the FactBlock ids behind each mark, and the spec is Vega-Lite over those rows. Nothing renders here. |
| Rendering | The caller's choice. Jupyter renders the spec as is. A web page passes it to vega-embed. A chat answer turns it into a PNG with `vl_convert.vegalite_to_png(spec)`. `views.pick(question)` chooses the view a question needs: why → evidence, change → stance, overall → track record. |
| `factblock.context(ids=True)` | The model's context, from the same bundle and the same as-of rule. |

The as-of rule is the same in both readers: `tests/test_duckdb.py` checks that the SQL macros and the Python library return the same rows, replacements, certificates and verdicts, and `tests/test_analysis_example.py` checks these views against the library.

**Recorded is not verified.** A `CAUSES` edge in this bundle says that Cramer said one thing causes another. The charts label links as recorded and colour statements only by verdicts, which here are mechanical: the sign of the price move at the call's horizon.

## Use your own data

Each view needs one thing from your data: the track record needs verdict rows, reversals need `replaces`, reasons need links, and the market drill-down needs a subject (`asset`) and a direction (`up` or `down`). Start from [`template.csv`](template.csv):

```
id,kind,said_at,due,text,asset,direction,speaker,source,replaces,target,outcome,decided_at
c1,prediction,2026-01-05,2026-03-31,Acme shares rise through Q1.,ACME,up,Ana,https://example.com/notes/1,,,,
c2,prediction,2026-02-10,2026-04-30,Acme shares fall after the guidance cut.,ACME,down,Ana,https://example.com/notes/2,c1,,,
,,,,,,,,,,c2,came_true,2026-05-01
```

```bash
factblock import my-calls.csv --backfill -o my-brain/
```

Set `BRAIN = "my-brain"` in the notebook and run it again. With the template you get the track record, one reversal and the stance chart for ACME. Reasons and the evidence view need links: they come from `factblock extract` on the transcripts, or from `edges.jsonl` rows you write yourself.
