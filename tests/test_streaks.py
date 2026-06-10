"""Pure-function tests for streak math — no DB, no HTTP."""

from app.utils.streaks import current_streak, longest_streak

# --- daily: current ---


def test_current_daily_empty():
    assert current_streak([], 'daily') == 0


def test_current_daily_single():
    assert current_streak(['2026-06-10'], 'daily') == 1


def test_current_daily_two_consecutive():
    assert current_streak(['2026-06-10', '2026-06-11'], 'daily') == 2


def test_current_daily_three_consecutive():
    assert current_streak(['2026-06-10', '2026-06-11', '2026-06-12'], 'daily') == 3


def test_current_daily_broken_streak_returns_recent_run():
    # Most recent contiguous block is just 2026-06-12 (one day) — gap before
    assert current_streak(['2026-06-10', '2026-06-12'], 'daily') == 1


def test_current_daily_counts_from_most_recent():
    # 2026-06-01..03 is an old streak; 2026-06-10..11 is the recent one
    assert (
        current_streak(
            ['2026-06-01', '2026-06-02', '2026-06-03', '2026-06-10', '2026-06-11'],
            'daily',
        )
        == 2
    )


def test_current_daily_unsorted_input():
    assert current_streak(['2026-06-11', '2026-06-10', '2026-06-12'], 'daily') == 3


def test_current_daily_dedupes_duplicates():
    assert current_streak(['2026-06-10', '2026-06-10', '2026-06-11'], 'daily') == 2


def test_current_daily_cross_month():
    assert current_streak(['2026-05-31', '2026-06-01'], 'daily') == 2


def test_current_daily_cross_year():
    assert current_streak(['2025-12-31', '2026-01-01'], 'daily') == 2


# --- daily: longest ---


def test_longest_daily_empty():
    assert longest_streak([], 'daily') == 0


def test_longest_daily_single():
    assert longest_streak(['2026-06-10'], 'daily') == 1


def test_longest_daily_finds_longest_run():
    dates = ['2026-06-01', '2026-06-02', '2026-06-03', '2026-06-10', '2026-06-11']
    assert longest_streak(dates, 'daily') == 3


def test_longest_daily_all_isolated():
    assert longest_streak(['2026-06-01', '2026-06-03', '2026-06-05'], 'daily') == 1


def test_longest_daily_dedupes():
    assert longest_streak(['2026-06-10', '2026-06-10'], 'daily') == 1


# --- weekly: current ---


def test_current_weekly_empty():
    assert current_streak([], 'weekly') == 0


def test_current_weekly_same_week_counts_once():
    # Both dates are in the same ISO week — should count as one
    assert current_streak(['2026-06-10', '2026-06-12'], 'weekly') == 1


def test_current_weekly_consecutive_weeks():
    # 2026-06-10 (Wed) → Monday-anchor 2026-06-08
    # 2026-06-17 (Wed) → Monday-anchor 2026-06-15
    assert current_streak(['2026-06-10', '2026-06-17'], 'weekly') == 2


def test_current_weekly_three_consecutive_weeks():
    assert current_streak(['2026-06-08', '2026-06-15', '2026-06-22'], 'weekly') == 3


def test_current_weekly_broken_streak():
    # Skip a week → current run is just one week
    assert current_streak(['2026-06-08', '2026-06-29'], 'weekly') == 1


def test_current_weekly_cross_year():
    # 2025-12-29 is Mon of last ISO week of 2025; 2026-01-05 is Mon of first 2026 week
    assert current_streak(['2025-12-29', '2026-01-05'], 'weekly') == 2


# --- weekly: longest ---


def test_longest_weekly_finds_longest_run():
    # Two short blocks: weeks 23-24 (2), then weeks 27-28-29 (3)
    dates = ['2026-06-08', '2026-06-15', '2026-07-06', '2026-07-13', '2026-07-20']
    assert longest_streak(dates, 'weekly') == 3
