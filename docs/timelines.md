# Timelines and graphs

Once your data is a bundle, one call draws what happened to each statement over time, as known on a day you pick.

```python
t = factblock.timeline("examples/promises/brain", as_of="2026-05-10", group_by="customer")
t                                                  # in Jupyter, the chart; hover for the history and block id, click for the source
t.save("promises.html")                            # .html needs nothing; .png and .svg need factblock[viz]
```

![Three sales promises grouped by customer: one kept, one broken, one open, as known on 10 May 2026](https://raw.githubusercontent.com/factagora/factblock/main/examples/analysis/img/timeline-bars.png)

One bar per statement, from the day it was said to the day it was replaced, judged or due, coloured by what became of it. The rest of its story (took effect, learned late, replaced by what, every verdict with its date) is in the tooltip and in `t.claims` and `t.events`. Read as of an earlier day and the verdicts, replacements and statements learned after it are not drawn.

Add a numeric series (prices, rates, any CSV with a date and a value) and the same statements sit on it where they were said:

```python
t = factblock.timeline("samples/cramer", as_of="2025-06-30", query="SPY").with_series("sp500.csv", "S&P 500")
```

![His calls on the market over the S&P 500 as known on 30 June 2025; the four settled calls are labelled, one right and three wrong](https://raw.githubusercontent.com/factagora/factblock/main/examples/analysis/img/timeline.png)

Values after the as-of day are dropped too. On the command line: `factblock timeline samples/cramer --as-of 2025-06-30 -q SPY --series sp500.csv -o spy.html`. The chart is a Vega-Lite spec (`t.spec()`), so it renders the same in a notebook, a web page (`react-vega`, `vega-embed`), or as an image in a chat answer. `t.to_html(inline=True)` is one self-contained page that renders with no network; `t.to_markdown()` is the same timeline as text for clients that cannot draw; `t.to_dict()` is the data for any other renderer, versioned as [`schemas/timeline.v1.schema.json`](https://github.com/factagora/factblock/blob/main/schemas/timeline.v1.schema.json). `samples/fed-funds-rate.csv` (FRED DFF, public domain) goes with `samples/rates`; the S&P 500 is licensed, so download it from FRED (`SP500`) yourself.

**In a chat answer.** An MCP server returns `t.to_mcp()` from its tool and serves `factblock.mcp_app_html()` as the resource `ui://factblock/timeline` (mime type and `_meta` in `factblock.timeline.MCP_APP_MIME` and `MCP_APP_META`; the tool's `_meta` is `MCP_APP_TOOL_META`). Hosts that support MCP Apps (Claude, ChatGPT, VS Code) then draw the chart inside the answer, in the host's theme; the rest show the markdown. The [tckg](https://github.com/factagora/tckg) `timeline` tool does exactly this. The same question asked as of two days:

<p><img src="https://raw.githubusercontent.com/factagora/factblock/main/examples/analysis/img/timeline-2025-04-30.png" width="49%" alt="As of 30 April 2025: 11 statements, the last call still open"> <img src="https://raw.githubusercontent.com/factagora/factblock/main/examples/analysis/img/timeline-2025-06-30.png" width="49%" alt="As of 30 June 2025: 16 statements, that call judged wrong on 6 June"></p>

On 30 April the last call ("bigger forces are going to crush the entire market") is open; on 30 June it has been judged wrong and five later calls have appeared. The April answer cannot use what was learned in May.

**What one statement rests on.** `factblock.graph(bundle, block_id, as_of)` draws the links around one statement: what it rests on above it, what came of it below, each row written in full, each dot coloured by what became of the statement. It walks `why()`, so a link or a verdict learned after `as_of` is not drawn.

```python
g = factblock.graph("samples/cramer", "fdc79a63b9b44a7f", as_of="2025-06-30", depth=2)
g.nodes, g.edges     # {id, label, type, when, resolution} and {id, from, to, label}: a graph renderer takes them as they are
```

![What "The stock market is positioned to move higher" rested on and led to, as known on 30 June 2025](https://raw.githubusercontent.com/factagora/factblock/main/examples/analysis/img/graph.png)
