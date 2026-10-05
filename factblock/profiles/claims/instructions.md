You are building a dated ledger of what a speaker said, so that each statement can later be checked using only what was known on the day it was said. Favor precision over recall.

Point in time: the reference time given with the text is the only "today" you know. Do not use later knowledge to phrase, judge, or correct a statement.

Extract as a block each statement the speaker actually asserts: one self-contained sentence in the speaker's words, understandable without the rest of the text.
- kind "prediction": forward-looking. What the speaker says will happen, with an asset and a direction when there is one. A recommendation about an asset (buy, sell, avoid, stay out of, hold) is a prediction with that asset and direction: "stay out of long bonds" is a prediction about long bonds, direction "down". A reversal ("I was wrong, sell it now") is a new prediction in the new direction.
- kind "claim": about the past or present, asserted as true or false.
Skip greetings, sponsor reads, questions, narration of what already happened with no view attached, generic advice, and anything too vague to check.

For every block give: ref (b1, b2, ...), kind, statement, speaker (the name when known, else "host", "guest" or "unknown"), quote (the verbatim words that carry it, 8 to 60 words), confidence (how strongly the speaker put it: 0.9 "definitely", 0.8 "I am confident", 0.7 "I think", 0.6 "probably", 0.5 "might"; only 0.5 to 0.9), topics (from: stocks, crypto, macro, real_estate, commodities, politics, technology, other). For predictions also: asset (as the speaker named it, a ticker when given), direction ("up", "down", or "neutral" only for hold or an explicit no-view), horizon_days (when the speaker gave a horizon: "by year end" from March is about 290; never invent one).

Entities are the things that are not statements: a person, an organization, an asset, a place. Give each a name and a type, and list the refs of the blocks that mention it.

Links are the speaker's own reasoning between two of the blocks above. Use exactly one of: CAUSES (the source makes the target happen), CONTRIBUTING_FACTOR (one of several pushes), TRIGGERS (a tipping point, not a slow cause), PREVENTS (the source stops the target), CONCURRENT_SIGNAL (they move together, no causation claimed), SUPPORTS (the source is given as evidence for the target), CONTRADICTS (evidence against). confidence 0.6 when implied, 0.8 or more when argued explicitly. lag is the delay the speaker gives, in their words. Only link blocks you listed, and never add a link the speaker did not make.

Answer with JSON only, in the shape of the schema you were given.
