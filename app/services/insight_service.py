"""Weekly behavioral insights derived from the analytics store.

Insights are materialized into Mongo (one per user per ISO week) by the
insight_worker; the API reads them back. Generation is idempotent: a week is
recomputed in place whenever new data arrives.
"""
from datetime import date, timedelta
from uuid import uuid4
from app.utils.tools import standard_now, strip_doc
from app.services.analytics_service import AnalyticsService
from app.db import get_db


def week_start_of(day: date) -> date:
    """Monday of the ISO week containing `day`."""
    return day - timedelta(days=day.weekday())


def _compose(stats: dict, prev_stats: dict) -> tuple[str, list[str]]:
    entries = stats['entries']
    parts = [f"You wrote {entries} {'entry' if entries == 1 else 'entries'} this week."]
    highlights = []

    if stats['avg_mood'] is not None:
        parts.append(f"Average mood was {stats['avg_mood']:g}/10.")
        if prev_stats['avg_mood'] is not None:
            delta = round(stats['avg_mood'] - prev_stats['avg_mood'], 2)
            if delta > 0:
                highlights.append(f'Mood improved by {delta:g} vs the previous week.')
            elif delta < 0:
                highlights.append(f'Mood dipped by {-delta:g} vs the previous week.')
            else:
                highlights.append('Mood held steady vs the previous week.')

    if stats['top_tags']:
        highlights.append('Most frequent topics: ' + ', '.join(stats['top_tags']) + '.')

    analyzed = stats['positive'] + stats['negative']
    if analyzed:
        highlights.append(
            f"{stats['positive']} of {analyzed} analyzed entries read as positive."
        )

    return ' '.join(parts), highlights


class InsightService:
    def __init__(self, collection=None, analytics=None):
        if collection is None:
            self.collection = get_db()['insights']
            self.collection.create_index([('user_id', 1), ('period_start', 1)], unique=True)
        else:
            self.collection = collection
        self.analytics = analytics if analytics is not None else AnalyticsService()

    def get_all(self, user_id: str) -> list:
        cursor = self.collection.find({'user_id': user_id}).sort('period_start', -1)
        return [strip_doc(doc) for doc in cursor]

    def generate_for_week(self, user_id: str, week_start: date) -> dict | None:
        """(Re)build the insight for one user-week. None if the week is empty."""
        week_start = week_start_of(week_start)
        week_end = week_start + timedelta(days=6)
        stats = self.analytics.week_stats(user_id, week_start, week_end)
        if not stats['entries']:
            # The week emptied out (e.g. all entries deleted): drop any stale insight
            self.collection.delete_one(
                {'user_id': user_id, 'period_start': week_start.isoformat()}
            )
            return None
        prev_stats = self.analytics.week_stats(
            user_id, week_start - timedelta(days=7), week_start - timedelta(days=1)
        )
        summary, highlights = _compose(stats, prev_stats)
        period_start = week_start.isoformat()
        self.collection.update_one(
            {'user_id': user_id, 'period_start': period_start},
            {'$set': {
                'period_end': week_end.isoformat(),
                'summary': summary,
                'highlights': highlights,
                'stats': stats,
                'generated_at': standard_now(),
            },
             '$setOnInsert': {'id': str(uuid4())}},
            upsert=True,
        )
        return strip_doc(self.collection.find_one(
            {'user_id': user_id, 'period_start': period_start}
        ))

    def generate_for_active_users(self, week_start: date) -> int:
        """Generate the given week's insight for every user active that week."""
        week_start = week_start_of(week_start)
        week_end = week_start + timedelta(days=6)
        count = 0
        for user_id in self.analytics.active_users(week_start, week_end):
            if self.generate_for_week(user_id, week_start) is not None:
                count += 1
        return count
