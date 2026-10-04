"""FactBlock table format: reference reader and validator (SPEC.md).

    scan(bundle, as_of, valid_at=None) -> Scan   # .nodes/.edges/.resolutions Arrow tables, .certificate
    validate(bundle) -> list[Check]              # one row per check id in SPEC section 2
    resolve(bundle, fact_key, as_of, valid_at=None, rules_as_of=None) -> dict   # SPEC 4.4
    write_parquet(bundle, out) -> Path          # JSONL bundle to the Parquet profile, SPEC 5.3
"""
from .bundle import Bundle
from .parquet import write_parquet
from .resolve import resolve
from .scan import Scan, scan
from .validate import Check, validate

__all__ = ["Bundle", "Scan", "scan", "Check", "validate", "resolve", "write_parquet"]
