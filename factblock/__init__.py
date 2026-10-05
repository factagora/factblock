"""FactBlock table format: reference reader and validator (SPEC.md).

    scan(bundle, as_of, valid_at=None) -> Scan   # .nodes/.edges/.resolutions Arrow tables, .certificate
    validate(bundle) -> list[Check]              # one row per check id in SPEC section 2
    resolve(bundle, fact_key, as_of, valid_at=None, rules_as_of=None) -> dict   # SPEC 4.4
    write_parquet(bundle, out) -> Path          # JSONL bundle to the Parquet profile, SPEC 5.3
    extract(text, observed_at, ...) -> dict      # the claims profile through a model you choose (extract.py)
    write_bundle(result, out, append=False)      # dicts to a JSONL bundle, growing one batch at a time
    why(bundle, node_id, as_of, valid_at=None, depth=3) -> dict   # the chain behind one block, SPEC 4.5
    leak(bundle, questions) -> dict               # answers that rest on blocks learned after the question was asked
    sync(bundle, store, as_of=None, push=True, pull=True) -> dict   # folder <-> a store (TckgStore, or yours) by identity
    to_claimreview(bundle, as_of, base_url=None) -> dict   # verdicts as schema.org ClaimReview JSON-LD, SPEC 9.2
    to_okf(bundle, as_of, out) -> Path             # one OKF concept document per visible node, SPEC 9.1
"""
from .bundle import Bundle, write_bundle
from .claimreview import to_claimreview
from .okf import to_okf
from .extract import extract, load_profile
from .leak import leak
from .parquet import write_parquet
from .resolve import resolve
from .scan import Scan, scan
from .sync import Store, TckgStore, sync
from .validate import Check, validate
from .why import why

__all__ = ["Bundle", "Scan", "scan", "Check", "validate", "resolve", "write_parquet", "extract", "load_profile", "write_bundle", "why", "leak", "sync", "Store", "TckgStore", "to_claimreview", "to_okf"]
