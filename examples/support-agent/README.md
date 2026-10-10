# Five support questions a date filter gets wrong

A support agent for a made-up SaaS company, Acme. Its knowledge changes the way real support knowledge does: a price is announced before it takes effect, the bot gives a wrong answer and a person corrects it, sales makes a promise, a policy memo reaches the help desk three weeks late, an API is retired.

Each question is asked on a date. The script builds the prompt context two ways and scores it:

- **Date filter**: what most memories do with time. Statements said on or before the question, keyword match, newest first.
- **FactBlock**: `factblock.context(brain, query, as_of=asked_at)`. Only what was known then, only what was in force then, with replacements and verdicts attached.

A context **fails** when it puts a stale statement into the prompt with nothing marking it stale, or leaves out the verdict the question asks for. No model is involved, so the result is the same on every run.

```bash
pip install --pre factblock
python examples/support-agent/run.py        # from a checkout of this repository
```

| | Asked | Question | What goes wrong with a date filter | Date filter | FactBlock |
|---|---|---|---|---|---|
| q1 | Feb 20 | How much does the Pro plan cost? | The $25 price was announced Feb 15 but starts Mar 1. It is the newest statement, so it leads | FAIL | PASS |
| q2 | Mar 20 | How many seats come with Pro? | The bot's own wrong answer ("10 seats") sits next to the correction with nothing saying which stands | FAIL | PASS |
| q3 | Jul 5 | Did SSO ship for customer A as promised? | The promise is there; whether it was kept is not | FAIL | PASS |
| q4 | Apr 10 | What refund window did the bot know on April 10? | The 14-day policy is dated April 1 but reached the help desk April 20. Replaying April 10 shows it anyway, and the bot looks wrong for saying 30 | FAIL | PASS |
| q5 | Jun 10 | Can I still use the v1 API? | "v1 is available to all plans" is still in the prompt after the shutdown | FAIL | PASS |

**0/5 vs 5/5.** What FactBlock put into the prompt for q2 and q3:

```
- 2026-03-14: The Pro plan includes 5 seats; more seats are billed per seat. (source: ticket correcting the bot's answer to customer B)
- 2026-03-12: The Pro plan includes 10 seats. (source: chat with customer B)
  replaced 2026-03-14 by: The Pro plan includes 5 seats; more seats are billed per seat.

- 2026-04-01: SSO for the Pro plan will ship by June 30 for customer A. (source: sales call with customer A)
  ended 2026-06-30
  verdict: did_not (decided 2026-07-01 by human:pm-lee)
```

## What makes the difference

Each failure is one field a timestamp column does not have:

| | Field | Where it is in the bundle |
|---|---|---|
| q1, q5 | When a statement is in force (`valid_from`, `valid_to`) | On the block |
| q2 | What replaced it | A `SUPERSEDES` row in `edges.jsonl` |
| q3 | What happened to it | A row in `resolutions.jsonl` |
| q4 | When we learned it (`known_at`), apart from when it was said | On the block, attested by a declared batch |

Corrections, verdicts and late arrivals are rows with their own `known_at`, so the same question asked on an earlier date does not see them. Try `factblock recall examples/support-agent/brain "SSO customer A" --as-of 2026-06-15`: the promise is open and has no verdict yet.

## Use it with your model

```python
import factblock
ctx = factblock.context("examples/support-agent/brain", "Pro seats", as_of="2026-03-20")
prompt = f"Answer from these notes. A note marked 'replaced' is no longer true.\n\n{ctx}\n\nQ: How many seats come with Pro?"
```

## The data

`brain/` is a FactBlock bundle written by hand: ten statements, four `SUPERSEDES` links, one verdict, and one backfill batch per source (pricing page, chat, ticket, sales call, legal memo, changelog). `questions.jsonl` holds the questions, their dates, and which statements must and must not be presented as current. `factblock validate examples/support-agent/brain` passes all thirteen checks.
