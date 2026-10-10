# Changelog

## Unreleased

### Changed
- The README's first screen is shorter: two lines of what it is, four commands, and the two examples in a few lines each. The full command list opens "How it reads".

## 1.0.0a12 (2026-10-11)

How the project introduces itself, after outside feedback. No code change.

### Changed
- The README, package description, CLI and `llms.txt` lead with "an open format for claims and their history": agent memory that tracks claims, evidence and changes, and answers what was known at any point in time. The track record moves to the second of two examples that open the README: a policy whose memo is dated April 1 but reaches the help desk April 20 (when it happened and when you learned it are different days), and two years of predictions judged against a baseline.
- The README no longer says other memories cannot keep this; it shows what FactBlock keeps instead.

## 1.0.0a11 (2026-10-10)

A hit rate next to the bar it has to clear.

### Added
- `track_record(...)` adds `baseline` to the total and to each group when verdicts carry a numeric `return` in their value (a price-horizon resolver writes `{return, excess_over_spy, direction}`): `always_up_hit_rate`, how often saying "up" every time would have been right on the same calls, and `avg_return_if_followed` / `avg_excess_if_followed`, the mean return of going long on "up" calls and short on "down" calls, outright and over SPY. `factblock track-record` prints it in one line. On `samples/cramer`: 54.7% right where "up" every time would have been 53.8%, while following the calls made +1.4% a call over SPY. A value stored as a JSON string, as a tckg export has it, is read the same.

## 1.0.0a10 (2026-10-10)

The track record of calls like the one in front of you, not only of everything.

### Added
- `track_record(..., ids=, speaker=)` and `factblock track-record --ids a,b,c --speaker <name>`: count only the statements you pass (say, what `recall` or a search found about the call you are weighing) or one speaker's. An id not known on as_of is refused. `left_out` counts picked statements that are neither judged nor a prediction or commitment, so a claim nobody judged is not silently dropped.

### Fixed
- `factblock track-record --by <field>`: the header lines up with the rows when the field name is longer than every group.

## 1.0.0a9 (2026-10-10)

One word, so the headline says exactly what `track-record` checks.

### Changed
- "On record before the outcome was known" is now "on record before they were resolved", in the README, package description and `llms.txt`, and `track-record` prints "on record before it was resolved". What is compared is the same as in 1.0.0a8: when a statement was written against its resolution's `decided_at`. An outcome can be known before it is resolved (a launch on 03-20, resolved on 03-28), so the old wording promised more than the check shows. "Resolved" is the word the format already uses (`resolutions.jsonl`). The `factblock resolve` command is unchanged and is still about declared facts, not verdicts.

## 1.0.0a8 (2026-10-10)

How claims, predictions and commitments turned out, and whether each was on record before its verdict.

### Added
- `factblock track-record <bundle> --as-of <date> [--by speaker]` and `factblock.track_record(bundle, as_of, by=)`: per group (a payload field such as speaker, or kind) how many statements were judged right, wrong or mixed, how many are open or overdue, and the hit rate (right / (right + wrong)), each statement counted once by its latest verdict known on that day. It also says how many were on record before their verdict: a row stamped live by a ledger, or captured in a batch before the verdict was decided, counts; one written later is reported as written from a cited source (checkable) or on the writer's word (hindsight not ruled out). On `samples/cramer`: 426 right, 353 wrong, and all 779 written later from a cited recording.

### Changed
- `factblock scan` says when judged statements are not listed because they were not in force that day (past due or replaced), and points to `--valid-at` and `track-record`. Before, their verdicts were listed under statements that did not appear.
- The README, package description and CLI lead with the track record: "Agent memory with a track record." The format and every other read are unchanged.

## 1.0.0a7 (2026-10-10)

From the first-use tests: matching by meaning, your own column and field names, and a format rule that catches verdicts on nothing.

**Upgrading from 1.0.0a6.** `validate` runs thirteen checks: SPEC I6 fails a verdict whose target is not in the bundle or that was decided before the statement was made. Bundles that relied on either now fail `validate`, `write_bundle` and `import`.

### Added
- `recall(..., embed=fn)`, `context(..., embed=)`, `timeline(..., embed=)` and `factblock recall --embed gemini|openai`: match by meaning as well as by words, so "price" finds a block that says "costs" (first-use test U1). The word ranking and the meaning ranking are fused (reciprocal rank, as tckg's search does); a block with no word in common is kept only when it is close to the best match, so an unrelated question still gets "nothing about it". `factblock.embedder("gemini"|"openai")` makes `fn` from the optional extras; any `fn(list[str]) -> list[list[float]]` works. Statement vectors are a search index, not part of the bundle: they are cached in `<bundle>/.factblock-cache/` by statement text, and vectors the bundle carries are used when `declarations.embedding.model` names the same model. No new dependency.
- `factblock import --map Claim=text,Date=said_at` and `from_records(..., columns={...})`: rows keep your column names; mapped columns are read as ours, the rest go to payload as before.
- `factblock leak --asked-key --evidence-key` and `leak(..., asked_key=, evidence_key=)`: a question set with its own field names. A set whose fields are named otherwise is refused with a pointer to these options, not read as leak-free.

### Changed
- SPEC invariant I6, checked by `validate` as `I6.target_exists` and `I6.after_statement`: every verdict names a node in the bundle and is not decided before that statement was made. A verdict on a missing block, or one dated before the promise it judges, used to pass; `write_bundle` and `factblock import` now refuse them with the check id. `validate` runs thirteen checks.

## 1.0.0a6 (2026-10-10)

A second chart: what one statement rests on and what came of it, for a notebook, a web page or a chat answer.

### Added
- `factblock.graph(bundle, block_id, as_of, depth=1)` and `factblock graph`: what one statement rests on (causes, supports, the call it replaced) and what came of it (effects, what it supported, the call that replaced it), as a chart. One row per statement written in full beside a narrow column of dots and arrows, so it reads in a chat column; dots coloured by what became of each statement. Read as of `as_of`, like `why()`: links and verdicts learned later are not drawn; calls past their horizon are drawn unless `valid_at` asks for what was in force. Rows use the field names a graph renderer takes as they are (`{id, label, type, when, resolution}`, `{id, from, to, label}`) plus the FactBlock detail, versioned as `schemas/graph.v1.schema.json`. Same outputs as a timeline: `.spec()`, `.save()`, `.to_markdown()`, `.to_mcp()` for the MCP Apps view.
- `why(..., in_force=False)` walks every block and link known by `as_of`, in force or not.

## 1.0.0a5 (2026-10-09)

### Changed
- `factblock.timeline` reads tckg's verdict words `hit` and `miss` as right and wrong, so a bundle exported from tckg draws its verdicts in colour.

## 1.0.0a4 (2026-10-09)

Charts from a bundle, the same in a notebook, a web page and a chat answer: `factblock.timeline` draws what happened to each statement as known on a day, and its MCP Apps view puts that chart inline in Claude or ChatGPT. Nothing that 1.0.0a3 reads or writes changed.

### Added
- `factblock.timeline(bundle, as_of, query="")` and `factblock timeline`: one bar per statement from the day it was said to the day it was replaced, judged or due, coloured by what became of it as known on `as_of`, rows optionally grouped (`group_by="customer"`); the full history of each statement is in the tooltip and the rows. `.with_series(csv)` draws the statements as points on a numeric series cut at `as_of`, the settled ones labelled. `.spec()` is Vega-Lite, Jupyter renders it directly, `.save()` writes `.html` with no dependencies or `.png`/`.svg` with the new `factblock[viz]` extra, and `.claims`/`.events`/`.to_dict()` are the rows for any other renderer, under the versioned contract `schemas/timeline.v1.schema.json` (`"schema": "factblock.timeline/v1"`). `.to_markdown()` is the same timeline as text for a chat answer, and `.to_html(inline=True)` (`--inline`) puts the Vega code in the page so it renders with no network, as an MCP Apps iframe requires; the page follows light or dark mode. `.to_mcp()` is a ready MCP tool result (markdown for the model, the rows as `structuredContent`, the spec in `_meta`) and `factblock.mcp_app_html()` is the MCP Apps view that draws it inline in Claude, ChatGPT and other hosts that support the UI extension: serve it as `ui://factblock/timeline` and point the tool at it (`factblock.timeline.MCP_APP_TOOL_META`). `samples/fed-funds-rate.csv` (FRED DFF, public domain) goes with `samples/rates`.
- `examples/analysis`: DuckDB + Jupyter over `samples/cramer`. Four findings a table of statements cannot give: a selection rule backtested as of each call vs with hindsight (+4.9% vs +9.3% a call), his hit rate as it was known each month vs a hindsight backtest (verdicts carry `known_at`), whether his 108 reversals helped (replaced calls are kept), whether reasoned calls were better (links and verdicts in one bundle); plus two drill-downs to the statements (one of them `factblock.timeline` over the S&P 500). Each view is SQL over the Parquet profile and returns its finding as the title, rows with the FactBlock id and source behind every mark, and a Vega-Lite spec, so a notebook, a web page and a chat answer render the same view. The notebook then asks a model the same data as of a date and traces each cited id to its recording. `template.csv` shows the input for your own calls.
- DuckDB macro `factblock_verdicts(bundle, as_of)`: the latest verdict per block among those known by `as_of`; `tests/test_duckdb.py` checks it against the Python reader on two samples.
- `factblock --version`.
- `context(..., ids=True)` starts each line with its block id, so a model can cite `[id]` and the caller can check the source.

## 1.0.0a3 (2026-10-09)

A write path for data you already have, and fixes from three first-use tests (a support bot over a CSV, a backtest with ingest lag, sales promises): every one of them had hit a silent wrong answer or had to copy the sample files to get data in. Format version unchanged: 1.0-draft.1, with `commitment` added as a core kind.

**Upgrading from 1.0.0a2.** `recall` and `context` now return every kind of statement by default, not only claims and predictions; pass `kinds=("claim", "prediction")` for the old behaviour. `leak` reads a date-only `asked_at` as the start of that day, so it can report more leaks than before. `write_bundle` validates before writing and raises instead of writing an invalid bundle. A row already in the folder is skipped on append instead of duplicated.

### Added
- `factblock demo <scene>`: an animated walkthrough of a bundle in the terminal (Rich, optional extra `factblock[demo]`). Scenes: `timeline` (scan at several dates), `why` (a chain growing, coloured by edge family), `replaced` (SUPERSEDES, then an earlier date), `verdict` (a block before it was said, open, settled; dates picked from the data), `leak` (a bench results file), `title`, `end`. Every number comes from the same reads as the plain commands; each panel names the command that gives it.
- `samples/demo.tape` records it with vhs into `samples/demo.gif` (README), `samples/demo.mp4` and `samples/demo-keyframe.png` (for slides). The plain-CLI recording is kept as `samples/demo-cli.gif` / `demo-cli.tape`.
- `bench/streamingqa/run.py` writes `results.json` next to itself; the committed one holds the published run (797 of 1,000).
- `factblock leak --json`.
- `factblock import <file.csv|.jsonl> -o <bundle>` and `factblock.from_records()`: rows you already have, no model. One row is a statement (`statement`/`text`, `asserted_at`/`said_at`, `valid_from`/`effective_from`, `valid_to`, `known_at`, `kind`, `replaces`) or a verdict (`target`, `outcome`, `decided_at`, `resolver`, `evidence`); other columns go to payload. `replaces` writes the SUPERSEDES edge. `known_at` comes from the row, else `--known-at`, else the day it was said with `--backfill`, else now.
- `examples/promises`: promises and verdicts from one CSV, read as of four dates (open, past due, broken, kept).
- `Scan.to_dicts("nodes"|"edges"|"resolutions")`: rows as dicts with the JSON columns parsed; `factblock scan --json` uses it, so a verdict's `value` is no longer double-encoded. `factblock.__version__`.
- README: a backtest recipe for data with ingest lag (publication is `said_at`, ingestion is `known_at`, no `--backfill`).

### Changed
- `write_bundle` takes plain rows: the manifest is optional, instants may be strings, dates or datetimes, `valid_from` defaults to `asserted_at`, and a row without `attestation` goes under a backfill batch the writer declares at its `known_at` (a row with no `known_at` is an error). The whole bundle is validated before anything is written, so a failing check raises `ValueError` and leaves the folder as it was. The input dicts are no longer modified.
- Docs say one rule for `known_at` everywhere: it is when you learned a row; give it honestly and let `import`, `extract` or `write_bundle` declare the batch (README, SKILL, AGENTS, SPEC glossary). Earlier text said "never set `known_at` yourself", which contradicted SPEC 6. README gains "Write rows you already have" and a table of the words for verdicts (verdict = resolution row, `outcome` its value, `resolve` is about declared facts).
- `recall` and `context` return every kind of statement by default, including kinds of your own (`commitment`, `promise`), and leave out only the things statements are about (`entity`, `factor`, `timeseries`, `episode`). Matches left out by kind are counted in `excluded`, and the CLI says so. `context` takes `kinds` too.
- `leak` reads a date-only `asked_at` as the start of that day (UTC), so a block learned later that day is a leak; reads still take the end of the day. Its text output shows the minute when a question and a block fall on the same day.
- Re-running `import` (or any `write_bundle(..., append=True)`) is a no-op for rows the folder already has, matched by identity (SPEC 6.1); the CLI reports how many were already there. The same id with different content is refused: blocks are never edited.
- `recall(query="")` lists every block, newest first; `recall(..., verdict="did_not"|"open"|"resolved")` and `factblock recall --verdict` filter by the latest visible verdict. Matching also searches the payload's text fields, so columns from `import` (customer, product) are found.
- Announced changes that are not in force yet are shown: `recall` items carry `upcoming` (the block that will replace them and from when) and `result["upcoming"]` lists other matching announcements; `context` writes `changes <date> to: ... (announced <date>)` and `(takes effect <date>)`.
- SPEC: `commitment` is a core kind (a promise to do something; `valid_to` is its deadline, as it is a `prediction`'s horizon), with the recommended verdicts `kept`, `partly_kept`, `broken`, `withdrawn`, rated in the ClaimReview projection. `import` takes a `due` column (a date means through the end of that day).
- `context` ends with `(as of <date>)` every time and no longer counts the blocks it hid: in a backtest even a count of later statements tells the model something. The certificate still has the counts. A line whose statement took effect after it was said notes `in force from <date>`.
- `recall(..., verdict="overdue")` and `--verdict overdue`: past the horizon or deadline with no verdict. `factblock recall` prints `due` and `ended` per item. Each `leak` question carries `day_only`, and the CLI marks those questions; its summary counts citations, not distinct blocks, and says so.
- `recall` keeps a prediction or commitment past its window, marked `ended`, with or without a verdict: the past-due, unresolved list. `context` shows `(due <date>)` before the deadline and `ended <date>, no verdict yet` after it.

### Fixed
- `context` said "replaced <date>" with the day the successor was said; it now gives the day the replacement took effect (the SUPERSEDES edge's `valid_from`) and adds "(announced <date>)" when they differ. `recall` items carry it as `superseded_by.since`.
- `context` never returns an empty string: with nothing matching it says `(nothing about '<query>' known as of <date>)`.
- `leak` no longer passes a question set it cannot read. A question without `asked_at` or an `evidence` list raises `ValueError` (it used to count as leak-free), and the CLI exits 1 when an evidence id is not in the bundle, as it does on a leak. Bad input prints one `factblock: error:` line instead of a traceback.
- `samples/rates`: c4, t1, t2 and the c4→c1 SUPERSEDES edge were learned (2024-09-15) before they were said (2024-09-18); batch b3 is now declared at 2024-09-20.

## 1.0.0a2 (2026-10-08)

Correctness fixes found by moving a real 46,000-row graph through the library and by a review against table formats, recall that carries corrections and verdicts into the prompt, and a first pass at making the library easy for coding agents to use correctly. Format version unchanged: 1.0-draft.1.

**Upgrading from 1.0.0a1.** The certificate's `masked` now counts only blocks learned after `as_of`; blocks known but not in force at `valid_at` are under `not_in_force`. `why()`'s certificate covers the walk, not the bundle. Code that read `masked` as "everything hidden" should add the two. `recall()` items gain keys; none were removed.

### Fixed
- `validate` accepted only `attestation.ledger`; SPEC I2 and 6 also allow a declared batch alone, which is what a non-ledger writer (an export script) produces. Both now pass, neither fails.
- `sync` compared edge and resolution instants as strings, so a ledger spelling `...57.89332+00:00` for a folder's `...57.893320+00:00` made a second run re-push 1,297 edges and pull them back into the folder as duplicates. Identity keys now compare instants, not spellings.
- Certificate (SPEC 4.2): `masked` counts only blocks learned after `as_of`; blocks known but not in force at `valid_at` move to a new `not_in_force` key. The Python reader counted both as masked and the DuckDB macro only the first, so the same read gave two certificates (samples/rates with `valid_at`: 4 vs 0). `factblock_certificate` gains `not_in_force_nodes`/`not_in_force_edges`; the DuckDB test now compares under `valid_at` too.
- `why` (SPEC 4.5): the certificate covers the walk (hidden edges at the chain's nodes and the neighbours they lead to), not the bundle. A five-block cramer chain carried `masked: {node: 1790, ...}`; it now carries what that chain hid.
- Graphiti adapter: an invalidated fact no longer leaks hindsight. Graphiti closes facts in place; writing `valid_to = invalid_at` on a row known at `created_at` hid the fact from reads between `created_at` and `expired_at`, when the store still believed it. The original row stays open and a closed copy `<uuid>~closed`, known at `expired_at`, SUPERSEDES it.
- Parquet rows are sorted by UTC instant (Arrow `sort_by`), not by the text of the timestamp; mixed offsets were out of order.
- `write_bundle` writes rows first and the manifest last via `os.replace`, so a reader never sees a batch declared before its rows.
- SPEC 3.7 says what both readers and tckg already do: `latest_observed` ranks by `known_at`, ties are a conflict. SPEC 5.4: an Iceberg/Delta/DuckLake snapshot at T is not an as-of read (backfills after T, expiry); apply `WHERE known_at <= T` to the current snapshot.

### Added
- `examples/support-agent`: five dated support questions (announced price, a bot answer corrected, a promise and its outcome, a policy learned late, a retired API), each answered from a date-filtered memory and from `factblock.context()`. A context fails when it presents a stale statement as current or omits the verdict: date filter 0/5, FactBlock 5/5. Deterministic, no model. `tests/test_support_example.py`.
- `factblock extract items.jsonl -o brain/`: one `{text, observed_at, speaker?, source?, known_at?}` per line, one batch per line, so a folder of dated transcripts or notes goes in with one command instead of a shell loop. `--observed-at`, `--speaker`, `--source-name` and `--known-at` become defaults that a line can override.
- `llms.txt` at the root, `AGENTS.md` for agents working in this repository, and `.claude/skills/factblock/SKILL.md`, a one-page skill to copy into a project.
- README "For coding agents": the API in one runnable block (kept honest by `tests/test_readme_agents.py`), three rules, and a table from Mem0 and Graphiti terms to FactBlock's.
- `py.typed`, type hints on the read functions (`BundleLike`, `Instant`), and docstrings whose first line says when to use each one.

### Changed
- `recall` and `context` carry what happened to each block since, as far as it was known at `as_of`: `superseded_by` (the replacing block, from a visible SUPERSEDES row), `verdict` (the latest visible resolution), `source` and `known_at`. `context` prints them as indented lines and marks blocks learned a day or more after they were said. A correction or verdict learned after `as_of` stays hidden, so the same query reads differently at different instants.
- `recall` keeps a block whose validity ended before `valid_at` when it has a verdict known by `as_of`, marked `ended`. A prediction or promise used to vanish from recall the moment its deadline passed, which is when its verdict arrives; on samples/cramer 17 settled calls came back.
- Error messages say what to do: a folder without `factblock.json` names the commands that make one; an unparseable instant shows the formats that work; an unknown `provider` lists the valid ones; a missing model SDK names the extra to install.
- `as_of` and `valid_at` accept `date` and `datetime` objects (a naive datetime is UTC, a date as `as_of` is the end of that day), not only strings.
- README: the logo in the title, `pip install --pre factblock` (the package is an alpha), and absolute links and images so the PyPI page renders them.

## 1.0.0a1 (2026-10-05)

First release on PyPI: the first public draft of the format (1.0-draft.1, 2026-10-04) and the reference library.

- Five invariants (three clocks, attested knowledge time, append-only, typed edges, declared facts) with one validator check id each.
- Logical model: node, edge, resolution, declarations (facts, backfill batches, edge types, embedding model).
- JSONL and Parquet profiles; Parquet files sorted by `known_at`, unknown fields kept in `extra`.
- Read semantics: as-of with certificate, `valid_at` defaulting to `as_of`, supersession, `resolve` by declared policy, expansion.
- Readers: the Python library (`scan`, `validate`, `resolve`, `write_parquet`) and the DuckDB macro pack.
- Writers: the tckg ledger (`GET /v1/export`) and the Graphiti adapter.

### Added
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
- `bench/streamingqa`: the hindsight number. StreamingQA's 36,378 dated questions as dated blocks; a time-ignorant top-5 recall leaks on 79.7% of questions (41.8% of picks), the as-of recall on none. `factblock.scan` now wraps a table-free `visible()` and `recall` keeps per-node word sets; a recall over 36,378 blocks takes under a second
