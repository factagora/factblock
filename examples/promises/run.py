"""Sales promises and whether they were kept, as known on any date. No model, no code beyond the reads.

    factblock import examples/promises/promises.csv --backfill -o examples/promises/brain   # once
    python examples/promises/run.py

A promise is a block of kind `commitment` whose valid_to is its deadline (the `due` column). The verdict
is a separate row (`kept`, `broken`, `partly_kept`, `withdrawn`) with its own decided_at, so a read as of
a date sees only the verdicts recorded by then. Past the deadline with no verdict, a promise stays in
recall marked `ended`: that is the "past due, unresolved" list."""
from pathlib import Path

import factblock

BRAIN = Path(__file__).resolve().parent / "brain"


def status(as_of, query=""):
    """{id: status} for the promises matching `query` as known on `as_of`."""
    out = {}
    for i in factblock.recall(BRAIN, query, as_of, kinds=("commitment",), limit=100)["items"]:
        v = i.get("verdict")
        out[i["id"]] = v["outcome"] if v else ("past due" if i.get("ended") else "open")
    return out


if __name__ == "__main__":
    for day in ("2026-03-15", "2026-04-10", "2026-05-10"):
        print(f"== as of {day}")
        print("promises to Globex:", status(day, "Globex"))
        print("broken:", [i["id"] for i in factblock.recall(BRAIN, "", day, kinds=("commitment",), verdict="broken")["items"]])
        print(factblock.context(BRAIN, "Globex", day))
        print()
