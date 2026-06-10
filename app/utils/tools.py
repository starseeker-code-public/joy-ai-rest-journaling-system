from datetime import UTC, datetime


def standard_now() -> str:
    return datetime.now(UTC).isoformat()


def strip_doc(doc: dict, *exclude: str) -> dict:
    """Return a copy of a MongoDB doc without `_id` and any extra excluded fields."""
    doc = dict(doc)
    doc.pop('_id', None)
    for field in exclude:
        doc.pop(field, None)
    return doc
