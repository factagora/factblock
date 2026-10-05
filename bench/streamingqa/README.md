# The hindsight number: StreamingQA

**On StreamingQA, a memory that ignores time rests on a block it learned after the question for 79.7% of
questions (top-5 recall, 1,000 questions). The same recall as of the question's date leaks on none, and
reports how much it hid to say so.**

## What is measured

[StreamingQA](https://github.com/google-deepmind/streamingqa) (DeepMind, 2022; data CC-BY 4.0) asks 36,378
questions during 2020 about English news published between 2007 and 2020. Every question carries the day it
was asked (`question_ts`) and the publication day of the article that answers it (`evidence_ts`), and no
article postdates its question. That makes it the right corpus for one question: **if a memory holds the
whole stream and does not know when it learned each piece, how often does it answer a question with
something it only learned later?**

`run.py` turns each question's evidence into one block (the answer as the statement, the question as the
quote), known when the article was published, so the folder is a FactBlock bundle with 36,378 blocks under
3,933 backfill batches (one per article date). Then, for a random sample of questions, it recalls the top
five blocks two ways:

| read | `as_of` |
|---|---|
| time-ignorant | far in the future: everything the folder holds |
| as-of | the day the question was asked |

The time-ignorant picks become a question set (`{asked_at, evidence: [ids]}`) and `factblock leak` counts
the questions that rest on a block learned after they were asked. The as-of read cannot leak by
construction: the number it reports is how many blocks it hid per question.

## Result

| read | questions that rest on a block learned after they were asked | leaked blocks among all picks |
|---|---|---|
| time-ignorant (`as_of` far in the future) | **797 / 1,000 = 79.7%** | 2,088 / 5,000 = 41.8% |
| as-of the question date | 0 / 1,000 = 0% by construction | 0; it hid 10,015 blocks per question on average to do so |

The split by StreamingQA's own `recent` (evidence within the question's year) and `past` labels:

| questions | n | time-ignorant leak rate |
|---|---|---|
| past (evidence older than the question's year) | 439 | 75.2% |
| recent (evidence within the question's year) | 561 | 83.2% |

## Reading it

- The number is a property of **the read, not the data**: the gold evidence never postdates the question.
  Every leak is a block the memory holds that did not exist for the asker. A benchmark that scores such a
  memory is scoring hindsight.
- Recall here is keyword matching (`factblock.recall`). A vector retriever would pick different blocks, but
  it has no `known_at` either; the point is the clock, not the ranker.
- The as-of read hides thousands of blocks per question. That is the cost of honesty, and the certificate
  carries it so nobody has to take the 0 on faith.

## Reproduce

```bash
uv sync
uv run python bench/streamingqa/run.py --questions 1000 --k 5 --seed 0   # downloads 7.5 MB, builds the bundle once
factblock leak bench/streamingqa/data/bundle bench/streamingqa/data/questions-k5-seed0.jsonl
```

Timing: about 1.6 s per question on one core (two recalls over 36,378 blocks each), 27 minutes for 1,000 questions. The bundle and question set are written under `bench/streamingqa/data/` (ignored by git).

Liška et al., *StreamingQA: A Benchmark for Adaptation to New Knowledge over Time in Question Answering
Models*, 2022 (arXiv:2205.11388). Data under CC-BY 4.0.
