# Show what an AI answer rested on, and what changed since

An expense agent answered on July 10, 2026 that a July 5 trip is reimbursed at 72.5 cents a mile. On July 13 the IRS announced 76 cents from July 1. Was the answer wrong when it was given, and what would you tell the user now? Record the answer as a block, link it to the blocks it used, and read it on any later day.

```bash
pip install --pre factblock
factblock sample --policies irs/
factblock import irs/mileage.csv --backfill -o brain/
factblock import irs/mileage-2026-07.csv --backfill -o brain/
```

```python
import factblock

used = factblock.recall("brain/", "mileage rate", as_of="2026-07-10", valid_at="2026-07-05", limit=1)["items"]
at = "2026-07-10T15:00:00Z"
factblock.write_bundle({
    "nodes": [{"id": "answer-1", "kind": "claim", "statement": "Reimburse the July 5 trip at 72.5 cents a mile.",
               "asserted_at": at, "known_at": at, "author": "agent:expenses"}],
    "edges": [{"source_id": i["id"], "target_id": "answer-1", "edge_type": "SUPPORTS", "asserted_at": at, "known_at": at} for i in used],
}, "brain/", append=True)
```

```text
$ factblock why brain/ answer-1 --as-of 2026-07-10 --depth 2
subject: answer-1  2026-07-10  Reimburse the July 5 trip at 72.5 cents a mile.
    support (SUPPORTS): irs-2026-01  2025-12-29  The IRS business standard mileage rate is 72.5 cents per mile.
        predecessor (SUPERSEDES): irs-2025  2024-12-19  The IRS business standard mileage rate is 70 cents per mile.
as of 2026-07-10  hidden: 1 edge  known_at declared by a writer: 3 rows in 3 batches

$ factblock why brain/ answer-1 --as-of 2026-07-20 --depth 2
subject: answer-1  2026-07-10  Reimburse the July 5 trip at 72.5 cents a mile.
    support (SUPPORTS): irs-2026-01  2025-12-29  The IRS business standard mileage rate is 72.5 cents per mile.
        predecessor (SUPERSEDES): irs-2025  2024-12-19  The IRS business standard mileage rate is 70 cents per mile.
        successor (SUPERSEDES): irs-2026-07  2026-07-13  The IRS business standard mileage rate is 76 cents per mile.
as of 2026-07-20  hidden: nothing  known_at declared by a writer: 4 rows in 4 batches
```

As of July 10 the answer rests on the 72.5-cent rate and nothing replaces it; the certificate says one link was hidden because it was learned later. As of July 20 the same walk shows the rate it rested on has a successor, 76 cents. The answer was right with what was known, and is out of date now. `factblock.why(...)` returns the same chain as rows, so an agent can list its answers whose support has a successor and correct them.

**What it does not do.** It does not decide that an answer is wrong. It shows what the answer rested on and what happened to those blocks; a verdict on the answer is your own row (`resolutions.jsonl`). The links are the ones you write; FactBlock does not infer them.
