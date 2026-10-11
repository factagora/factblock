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

A date-only `asked_at` means the start of that day, so news ingested later that day counts as a leak; give a timestamp to be exact. A date-only `as_of` means the end of that day for reads, so build each question's context with its full timestamp and give `leak` the same one. `leak` checks knowledge time and validity. Evidence that was knowable but already replaced when the question was asked is not a leak; `recall` marks it `superseded_by` if you need to catch that too.

On [StreamingQA](https://github.com/factagora/factblock/tree/main/bench/streamingqa) (1,000 sampled questions about dated news, keyword recall, top 5), a recall that ignores time cites a block learned after the question for **79.7% of questions**; the same recall as of the question date cites none, by construction, and says how much it hid. This measures leakage, not answer accuracy. If your memory benchmark never reports this number, it is measuring hindsight.

**Backtests with ingest lag.** When each item has a publication time and the time your system ingested it, publication is `said_at` and ingestion is `known_at`. Do not pass `--backfill`: it would date every item to its publication and erase exactly the lag you are testing.

```
# news.jsonl: {"id": "n2", "text": "Acme cuts Q1 guidance to $1.0B.", "said_at": "2025-03-20T21:00:00Z", "known_at": "2025-03-21T02:00:00Z", "replaces": "n1"}
factblock import news.jsonl -o news/
factblock leak news/ questions.jsonl      # {"id": "q2", "asked_at": "2025-03-21T00:00:00Z", "evidence": ["n2"]} per line; --evidence-key for another name
```

**What it does not do.** It checks the evidence ids you give it, not the text the model wrote: an answer that states 76 cents without citing a block is not caught. It measures leakage, not whether the answer is right.
