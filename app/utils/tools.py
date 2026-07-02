from datetime import date, datetime, timezone
from flask import request


def standard_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def json_body() -> dict:
    """Request JSON as a dict; non-object payloads (strings, lists) count as empty."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def strip_doc(doc: dict, *exclude: str) -> dict:
    """Return a copy of a MongoDB doc without `_id` and any extra excluded fields."""
    doc = dict(doc)
    doc.pop('_id', None)
    for field in exclude:
        doc.pop(field, None)
    return doc
