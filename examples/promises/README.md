# Promises and whether they were kept

Sales makes promises to customers ("feature X by date Y"). Later, product records whether each one was kept. An assistant asked on any date should know which promises were open, which were kept, which were broken, and which are past due with nobody saying, as known on that date.

The data is one CSV, promises and verdicts together. No model, no code to build the bundle:

```
id,kind,said_at,due,text,speaker,customer,target,outcome,decided_at,resolver
p1,commitment,2026-02-01,2026-04-30,Audit log export for Globex by April 30.,Sam,Globex,,,,
p2,commitment,2026-02-15,2026-03-31,SAML SSO for Initech by March 31.,Sam,Initech,,,,
p3,commitment,2026-03-05,2026-06-30,EU data residency for Globex by June 30.,Priya,Globex,,,,
,,,,,,,p2,broken,2026-04-02,human:lee
,,,,,,,p1,kept,2026-05-03,human:lee
```

```bash
pip install --pre factblock
factblock import examples/promises/promises.csv --backfill -o examples/promises/brain
python examples/promises/run.py
factblock recall examples/promises/brain "" --as-of 2026-04-10 --verdict broken
```

| As of | Globex | Broken | Past due, no verdict |
|---|---|---|---|
| 2026-03-15 | p1 open, p3 open | none | none |
| 2026-04-01 | p1 open, p3 open | none | p2 (due 03-31, verdict not recorded until 04-02) |
| 2026-04-10 | p1 open, p3 open | p2 | none |
| 2026-05-10 | p1 kept, p3 open | p2 | none |

What `context()` puts into the prompt for "Globex" as of 2026-05-10:

```
- 2026-03-05 Priya: EU data residency for Globex by June 30. (due 2026-06-30)
- 2026-02-01 Sam: Audit log export for Globex by April 30.
  ended 2026-04-30
  verdict: kept (decided 2026-05-03 by human:lee)
```

## How it is modelled

- A promise is a block of kind `commitment`. Its `valid_to` is the deadline: the `due` column, through the end of that day.
- A verdict is a separate row in `resolutions.jsonl` (`kept`, `partly_kept`, `broken`, `withdrawn`), with its own `decided_at` and `known_at`. A read as of a date sees only the verdicts recorded by then, so on April 1 the SSO promise is past due and unresolved, and on April 10 it is broken.
- Past its deadline, a commitment stays in `recall` marked `ended`, with its verdict or without one. Hiding it would hide the answer to "did we keep it?".
- `recall(..., verdict="broken")`, `"open"` or `"resolved"` filters by the latest visible verdict; an empty query lists everything.
