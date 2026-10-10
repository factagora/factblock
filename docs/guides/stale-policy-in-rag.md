# Your RAG answers with a rate that changed

A date filter (`said_at <= question date`, newest first) is how most memories handle time. It goes wrong twice with the IRS business mileage rate: when a change is announced before it takes effect, and when the question is about an earlier day than the day it is asked. FactBlock reads each row's own validity (`valid_from`, replacements) as of the day you ask.

```bash
pip install --pre factblock
factblock sample --policies irs/
factblock import irs/mileage.csv --backfill -o brain/
factblock import irs/mileage-2026-07.csv --backfill -o brain/
```

```python
import csv, factblock

rows = [r for f in ("irs/mileage.csv", "irs/mileage-2026-07.csv") for r in csv.DictReader(open(f))]

def date_filter(asked):                      # newest statement said on or before the question
    return max((r for r in rows if r["said_at"] <= asked), key=lambda r: r["said_at"])["text"]

for asked, trip in (("2022-06-20", "2022-06-20"), ("2026-07-20", "2026-06-20"), ("2026-07-20", "2026-07-05")):
    answer = factblock.recall("brain/", "mileage rate", as_of=asked, valid_at=trip, limit=1)["items"][0]["statement"]
    print(f"asked {asked}, trip {trip}: date filter {date_filter(asked).split(' is ')[1]} / FactBlock {answer.split(' is ')[1]}")
```

```text
asked 2022-06-20, trip 2022-06-20: date filter 62.5 cents per mile. / FactBlock 58.5 cents per mile.
asked 2026-07-20, trip 2026-06-20: date filter 76 cents per mile. / FactBlock 72.5 cents per mile.
asked 2026-07-20, trip 2026-07-05: date filter 76 cents per mile. / FactBlock 76 cents per mile.
```

The first question is asked on June 20, 2022: 62.5 cents was announced on June 9 but applies from July 1, so the right rate is still 58.5. The second asks in July 2026 about a June trip: 76 cents applies from July 1, so June is 72.5. The third is the one a date filter gets right. For your agent's prompt, `factblock.context(...)` takes the same arguments and returns the same blocks as lines, with what replaced each one.

**What it does not do.** Matching is by words unless you pass `embed=` (see the README). Your rows need their dates: `said_at`, and `effective_from` when it differs. FactBlock does not decide which rate is right; it returns what was in force on the day, as you recorded it.
