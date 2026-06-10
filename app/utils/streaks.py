"""Pure-function streak math for habit completions.

Inputs are lists of ISO date strings (YYYY-MM-DD); outputs are integer streak
lengths. The functions deduplicate and sort internally so callers don't need
to pre-process.
"""
from datetime import date, datetime, timedelta


def _parse(dates: list[str]) -> set[date]:
    return {datetime.strptime(d, '%Y-%m-%d').date() for d in dates}


def _monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _normalize(dates: list[str], cadence: str) -> list[date]:
    """Return sorted, deduplicated list of anchor dates per cadence."""
    parsed = _parse(dates)
    if cadence == 'weekly':
        anchors = {_monday_of(d) for d in parsed}
    else:  # daily
        anchors = parsed
    return sorted(anchors)


def _step_days(cadence: str) -> int:
    return 7 if cadence == 'weekly' else 1


def current_streak(dates: list[str], cadence: str = 'daily') -> int:
    """Length of the most recent unbroken run of completions.

    Note: this is *time-independent*. A 5-day run that ended six months ago
    still returns 5. To compute "active streak ending today," combine this
    with a freshness check on the most recent date in `dates`.
    """
    anchors = _normalize(dates, cadence)
    if not anchors:
        return 0
    step = _step_days(cadence)
    streak = 1
    for i in range(len(anchors) - 1, 0, -1):
        if (anchors[i] - anchors[i - 1]).days == step:
            streak += 1
        else:
            break
    return streak


def longest_streak(dates: list[str], cadence: str = 'daily') -> int:
    """Longest unbroken run of completions anywhere in the history."""
    anchors = _normalize(dates, cadence)
    if not anchors:
        return 0
    step = _step_days(cadence)
    longest = current = 1
    for i in range(1, len(anchors)):
        if (anchors[i] - anchors[i - 1]).days == step:
            current += 1
            longest = max(longest, current)
        else:
            current = 1
    return longest
