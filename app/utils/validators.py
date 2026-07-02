"""Shared field validators used by the domain services. All raise ValueError."""
import re
from datetime import date

_ISO_DATE = re.compile(r'\d{4}-\d{2}-\d{2}')


def require_string(value, field: str) -> str:
    """A non-empty string, trimmed."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field} must be a non-empty string')
    return value.strip()


def parse_iso_date(value, field: str) -> date:
    """Strictly YYYY-MM-DD (fromisoformat alone also accepts e.g. '20261231')."""
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
        raise ValueError(f'{field} must be a YYYY-MM-DD string')
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f'{field} must be a YYYY-MM-DD string')
