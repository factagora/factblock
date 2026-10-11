# samples/cramer

Jim Cramer, as a FactBlock bundle: 2,091 statements from CNBC Television recordings between 2024-09 and
2026-09, 1,169 links he drew between them, and 779 priced calls scored at their horizon. This is the
data behind one of the public brains on [factagora.ai/brains](https://factagora.ai/brains).

- A statement is known when its recording was published: one backfill batch per video (`yt:<id>`),
  declared at the video's `published_at`, so `--as-of 2025-01-01` shows what a viewer could have heard
  by then. Every block links to the recording and the timestamp (`payload.source`).
- A verdict is known on the day the horizon price settled (`settle:<date>`): a call is `came_true` or
  `did_not` by the sign of the return at the horizon (`method: price_horizon`), and as of any earlier
  date it is still open.
- Statements are paraphrases produced by a model from public recordings and carry the original quote;
  they are the speaker's claims, not ours, and the verdicts are mechanical.

```bash
factblock scan samples/cramer --as-of 2025-01-01 | head
factblock recall samples/cramer "Nvidia data center" --as-of 2025-01-01
factblock why samples/cramer 1b77a1a885470207 --as-of 2026-09-10
factblock to-claimreview samples/cramer --as-of 2025-06-01 | head -40
```

## What comes out

```
$ factblock scan samples/cramer --as-of 2025-01-01 | head -1
as of 2025-01-01  hidden: 1775 nodes, 1025 edges, 753 resolutions  not in force: 15 nodes  known_at declared by a writer: 471 rows in 52 batches

$ factblock why samples/cramer 1b77a1a885470207 --as-of 2026-09-10
subject: 1b77a1a885470207  2025-07-17  The current data center buildout is the largest construction boom since World War II.
    effect (CAUSES): c43aac6a842836bf  2025-07-17  Lead contractors such as ABB and Legrand are receiving strong data center orders.
        effect (CAUSES): 041ef1dfd5dbb6df  2025-07-17  Companies involved in the data center buildout, such as Eaton and Parker-Hannifin, are receiving a large number of new orders.
            effect (CAUSES): 2751ba237ecd5415  2025-07-17  Parker-Hannifin is a good stock to own.
            effect (CAUSES): 7d3af08ba4f4f027  2025-07-17  Eaton is a good stock to own.
as of 2026-09-10  hidden: nothing  known_at declared by a writer: 5 rows in 1 batch
```

A call and its verdict carry separate clocks, so the same read gives different answers on different days:

```
$ factblock recall samples/cramer "Nvidia business growing slowing" --as-of 2024-12-10 --limit 1
66027d5985bf9605 claim       2024-09-11  Nvidia's business is currently growing, not slowing down.   (Jim Cramer)
                           verdict: came_true (2024-12-10)
```

As of 2024-11-01 the call is open. As of 2024-12-10 it came true. As of 2024-09-10 it does not exist yet. `to-claimreview samples/cramer --as-of 2025-06-01` writes the 197 verdicts known by then as schema.org JSON-LD.

Produced by `randy-note/scripts/influencer-to-factblock.py` from the influencer backtest data.
