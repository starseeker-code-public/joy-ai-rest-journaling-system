"""Aggregate journal analytics backed by ClickHouse.

The analytics_sink worker mirrors journal events from RabbitMQ into an
append-only events table; the API reads aggregates from it.

Aggregations reduce the event log to the latest state per journal entry
(argMaxIf over created/updated events, excluding entries whose log contains
a delete), so edits don't double-count and mood lands on the entry's own
date rather than the ingestion time.
"""
import os
from datetime import date, datetime, timezone

TABLE = 'journal_events'

SCHEMA = f'''
CREATE TABLE IF NOT EXISTS {TABLE} (
    event_time DateTime64(6, 'UTC'),
    event_type String,
    journal_id String,
    user_id String,
    entry_date Nullable(Date),
    mood Nullable(Int32),
    tags Array(String),
    sentiment_label String,
    sentiment_score Nullable(Float64)
)
ENGINE = MergeTree
ORDER BY (user_id, event_time)
'''

COLUMNS = [
    'event_time', 'event_type', 'journal_id', 'user_id',
    'entry_date', 'mood', 'tags', 'sentiment_label', 'sentiment_score',
]

# Latest journal state derived from the event log, one row per live entry
_LATEST_STATE = f'''
    SELECT journal_id,
           argMaxIf(mood, event_time,
                    event_type IN ('journal.created', 'journal.updated')) AS mood,
           argMaxIf(entry_date, event_time,
                    event_type IN ('journal.created', 'journal.updated')) AS entry_date,
           argMaxIf(tags, event_time,
                    event_type IN ('journal.created', 'journal.updated')) AS tags,
           max(event_type = 'journal.deleted') AS deleted
    FROM {TABLE}
    WHERE user_id = %(user_id)s
    GROUP BY journal_id
'''


def _default_client():
    import clickhouse_connect
    return clickhouse_connect.get_client(
        host=os.getenv('CLICKHOUSE_HOST', 'localhost'),
        port=int(os.getenv('CLICKHOUSE_PORT', '8123')),
    )


def _parse_entry_date(value):
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


class AnalyticsService:
    def __init__(self, client=None):
        # Lazy: clickhouse_connect pings the server on get_client, and the
        # API must be able to boot while ClickHouse is down.
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = _default_client()
        return self._client

    def ensure_schema(self) -> None:
        self.client.command(SCHEMA)

    def record_event(self, event_type: str, payload: dict) -> None:
        sentiment = payload.get('sentiment') or {}
        row = [
            datetime.now(timezone.utc),
            event_type,
            payload['id'],
            payload['user_id'],
            _parse_entry_date(payload.get('date')),
            payload.get('mood'),
            payload.get('tags') or [],
            sentiment.get('label') or '',
            sentiment.get('score'),
        ]
        self.client.insert(TABLE, [row], column_names=COLUMNS)

    def mood_trend(self, user_id: str, days: int = 30) -> list[dict]:
        result = self.client.query(
            f'''SELECT entry_date AS day,
                       round(avg(mood), 2) AS avg_mood,
                       count() AS entries
                FROM ({_LATEST_STATE})
                WHERE deleted = 0
                  AND mood IS NOT NULL
                  AND entry_date >= today() - %(days)s
                GROUP BY day
                ORDER BY day''',
            parameters={'user_id': user_id, 'days': days},
        )
        return [
            {'date': day.isoformat(), 'avg_mood': avg_mood, 'entries': entries}
            for day, avg_mood, entries in result.result_rows
        ]

    def tag_frequency(self, user_id: str, limit: int = 10) -> list[dict]:
        result = self.client.query(
            f'''SELECT arrayJoin(tags) AS tag, count() AS uses
                FROM ({_LATEST_STATE})
                WHERE deleted = 0
                GROUP BY tag
                ORDER BY uses DESC, tag ASC
                LIMIT %(limit)s''',
            parameters={'user_id': user_id, 'limit': limit},
        )
        return [{'tag': tag, 'count': uses} for tag, uses in result.result_rows]
