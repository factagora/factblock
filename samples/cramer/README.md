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

Produced by `randy-note/scripts/influencer-to-factblock.py` from the influencer backtest data.
