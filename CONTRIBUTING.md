# Contributing

FactBlock is a format first and a library second. The spec ([SPEC.md](./SPEC.md)) is normative; the
Python package is the reference implementation. A change to one usually means a change to the other.

## Before you open a pull request

```bash
uv sync
for t in tests/test_*.py; do uv run python $t; done     # the same checks CI runs
uv run python -m factblock validate samples/rates
```

Every test file is one script that prints `PASS ...` or raises. Add a check to the file that covers
what you changed, or a new `tests/test_<thing>.py` and a line in `.github/workflows/test.yml`.

## What goes where

- **A new field or rule**: SPEC.md first (section 3 or 4), with its validator check id in section 2 or 8,
  then `factblock/validate.py` and a case in `tests/test_rates.py`. Minor versions add fields; they never
  change the meaning of an existing one (section 7).
- **A new writer or reader** (an adapter for another store or feed): `factblock/adapters/<name>.py`,
  one test with a synthetic fixture under `tests/fixtures/`, a line in SPEC.md section 10. The one rule
  every writer keeps is section 6: never invent `known_at`; declare a backfill batch instead.
- **A new projection** (another standard a bundle should speak): `factblock/<name>.py`, a subsection
  under SPEC.md section 9 with the mapping table and what the projection loses.
- **Extraction rules** live in `factblock/profiles/claims/` as three files, not in code, so that other
  languages run the same extraction. Change the files; keep `extract.py` thin.

No new runtime dependencies without a reason in the pull request. The core depends on `pyarrow` only;
model SDKs are optional extras.

## Developer Certificate of Origin

Contributions are accepted under the [Developer Certificate of Origin 1.1](https://developercertificate.org/):
by signing off a commit you state that you wrote the change or have the right to submit it under the
project's license (Apache-2.0). Sign off with `git commit -s`, which adds

```
Signed-off-by: Your Name <you@example.com>
```

There is no separate contributor agreement.

## Style

Short files, plain functions, no abstractions for one caller. Prose in English, sentence case, no em
dashes. A module docstring says what the file does and which SPEC section it implements.
