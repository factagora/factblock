# Twelve tax questions vector RAG gets wrong

A CPA firm's knowledge changes the way tax law does: a rate changed retroactively, but only for property bought after a date; research costs are treated one way at home and another abroad; an election opens and its deadline passes; BOI reporting was on, off, on, off, on, then gone for U.S. companies; a disaster postponement covers one county and not the next. Every row in [`rules.csv`](rules.csv) is public U.S. tax law with its source.

Each question is asked on a date, about a date, for a client with facts. Three ways to answer it with the same model (gemini-2.5-flash, temperature 0), the same question, the same "today is" and multiple-choice options, so scoring is exact:

- **Model only**: the question, nothing else.
- **Vector RAG**: the four rows nearest in meaning to the question. What most retrieval stacks do; it does not know which row was in force when, or for whom.
- **FactBlock**: the rows that apply to this client (`applies_if`), read as of the day asked (`as_of`), for the day the question is about (`valid_at`), replacements marked.

FactBlock also answers without a model: of the rows in force and not replaced, the most specific one, with its source. Same answer on every run.

```bash
pip install --pre 'factblock[gemini]'
python examples/tax-rules/run.py          # from a checkout: the model-free answer, 12/12
python examples/tax-rules/run.py --llm    # also the three model arms (GEMINI_API_KEY, or GOOGLE_GENAI_USE_VERTEXAI=1 + GOOGLE_CLOUD_PROJECT)
```

| | Asked | Question | Right | Model only | Vector RAG | FactBlock + model | FactBlock, no model |
|---|---|---|---|---|---|---|---|
| q1 | 2025-03-15 | Client A acquired equipment on February 10 2025 and placed it in service in March 2025. What bonus depreciation rate applies on its 2025 return? | 40% | 3/3 | 0/3 | 3/3 | 3/3 |
| q2 | 2026-10-12 | Client A acquired equipment on February 10 2025 and placed it in service in March 2025. What bonus depreciation rate applies on its 2025 return? | 100% | 0/3 | 3/3 | 3/3 | 3/3 |
| q3 | 2026-10-12 | Client B signed a binding purchase contract for equipment on December 5 2024 and placed it in service in March 2025. What bonus depreciation rate applies on its 2025 return? | 40% | 2/3 | 3/3 | 3/3 | 3/3 |
| q4 | 2026-10-12 | A U.S. C corporation paid software developers in Korea for research in tax year 2025. How are those research costs treated on the 2025 return? | amortize over 15 years | 3/3 | 3/3 | 3/3 | 3/3 |
| q5 | 2026-10-12 | A U.S. C corporation paid software developers in California for research in tax year 2025. How are those research costs treated on the 2025 return? | deduct immediately | 0/3 | 3/3 | 3/3 | 3/3 |
| q6 | 2026-03-01 | A small business (gross receipts $5 million) amortized its 2023 domestic research costs. Can it still amend its 2023 return to deduct them under 174A? | yes | 0/3 | 3/3 | 3/3 | 3/3 |
| q7 | 2026-10-12 | A small business (gross receipts $5 million) amortized its 2023 domestic research costs. Can it still amend its 2023 return to deduct them under 174A? | no | 3/3 | 3/3 | 3/3 | 3/3 |
| q8 | 2025-01-10 | A Delaware C corporation formed in 2023 has not filed a BOI report. Does it have to file one now? | not required (injunction) | 1/3 | 0/3 | 3/3 | 3/3 |
| q9 | 2025-03-01 | A Delaware C corporation formed in 2023 has not filed a BOI report. Does it have to file one now? | required by March 21 2025 | 0/3 | 2/3 | 3/3 | 3/3 |
| q10 | 2026-10-12 | A Delaware C corporation formed in 2023 and wholly owned by Korean founders living in Seoul has not filed a BOI report. Does it have to file one now? | exempt | 0/3 | 3/3 | 3/3 | 3/3 |
| q11 | 2025-03-01 | A calendar-year C corporation located in Fullerton, Orange County, California owes tax for 2024. By when must it pay? | April 15 | 3/3 | 3/3 | 3/3 | 3/3 |
| q12 | 2025-03-01 | A calendar-year C corporation located in Pasadena, Los Angeles County, California owes tax for 2024. By when must it pay? | October 15 | 0/3 | 3/3 | 3/3 | 3/3 |
| | | **Total, three runs** | | **15/36** | **29/36** | **36/36** | **36/36** |

## Where vector RAG went wrong

- **q1, asked March 15 2025: what was right the day the firm advised?** The nearest rows include the July 2025 law (100%), which did not exist yet. A firm replaying its own advice cannot tell a mistake from a law that changed later.
- **q8, asked January 10 2025: does a Delaware corporation file BOI now?** Seven rows about BOI; the four nearest leave out December 26 (injunction reinstated), so the answer is the deadline it had cancelled.

The model alone misses what came after its training (100% bonus, 174A, the BOI exemption, the Los Angeles postponement).

## Advice to re-send

The firm told Client A on March 15 2025 that its equipment got 40%. That memo rests on a row the July 2025 law replaced for property acquired after January 19 2025, which Client A's was. `renotify()` lists it as of today, and not as of June 1 2025, before the law changed.

## What it does not do

- `applies_if` is checked in this script, before the bundle is read: each client gets its own bundle of the rows that apply, so a replacement that covers other clients does not mark this client's rule as replaced. It is not in the format yet.
- The rows are a sample, not tax advice, and not complete: each says what the source says, shortened.
- Matching is by words. Twenty rows and one topic per question are the easy case for vector search; a real knowledge base has many more near-duplicates from different years.
