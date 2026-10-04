"""FactBlock table format: reference reader and validator (SPEC.md).

    scan(bundle, as_of, valid_at=None) -> Scan   # .nodes/.edges/.resolutions Arrow tables, .certificate
    validate(bundle) -> list[Check]              # one row per check id in SPEC section 2
"""
from .bundle import Bundle
from .scan import Scan, scan
from .validate import Check, validate

__all__ = ["Bundle", "Scan", "scan", "Check", "validate"]
