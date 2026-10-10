# Evaluate an agent only on what was known at the time

An evaluation set asks: "On July 10, 2026, what is the mileage rate for a July 5 trip?" If the evidence behind an answer includes the 76-cent rate, the answer used something nobody knew on July 10: it was announced on July 13. The score then measures hindsight. `leak` checks every answer's evidence against the question's date.

```bash
pip install --pre factblock
factblock sample --policies irs/
factblock import irs/mileage.csv --backfill -o brain/
factblock import irs/mileage-2026-07.csv --backfill -o brain/
```

```python
import factblock

questions = [
    {"id": "q1", "asked_at": "2026-07-10T15:00:00Z", "evidence": ["irs-2026-07"]},   # cites the 76-cent rate
    {"id": "q2", "asked_at": "2026-07-10T15:00:00Z", "evidence": ["irs-2026-01"]},   # cites the 72.5-cent rate
]
r = factblock.leak("brain/", questions)
print(f"{r['leaked_questions']} of {r['questions']} answers rest on blocks learned after the question")
for q in r["per_question"]:
    for block in q["leaked"]:
        print(q["id"], block["id"], "known", block["known_at"][:10])
```

```text
1 of 2 answers rest on blocks learned after the question
q1 irs-2026-07 known 2026-07-13
```

The same check runs from the command line on a JSONL file (`factblock leak brain/ questions.jsonl`) and exits non-zero on a leak, so it fits in CI. To build answers that cannot leak, retrieve with `as_of` set to the question's time: `factblock.context("brain/", "mileage rate", as_of="2026-07-10T15:00:00Z", valid_at="2026-07-05")`.

**What it does not do.** It checks the evidence ids you give it, not the text the model wrote: an answer that states 76 cents without citing a block is not caught. It measures leakage, not whether the answer is right.
