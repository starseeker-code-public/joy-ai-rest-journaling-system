from collections import defaultdict
from datetime import date, timedelta
from uuid import uuid4
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from app.utils.tools import standard_now, strip_doc, utc_today
from app.utils.validators import parse_iso_date, require_string
from app.db import get_db

VALID_FREQUENCIES = {'daily', 'weekly'}


def _validate_frequency(frequency):
    if frequency is None:
        return 'daily'
    if frequency not in VALID_FREQUENCIES:
        raise ValueError(f'frequency must be one of {sorted(VALID_FREQUENCIES)}')
    return frequency


def _validate_date(value) -> str:
    """Accept a YYYY-MM-DD string; default to today (UTC).

    Days are UTC-based, but clients ahead of UTC may legitimately be one
    calendar day ahead, so allow up to utc_today() + 1.
    """
    if value is None:
        return utc_today().isoformat()
    parsed = parse_iso_date(value, 'date')
    if parsed > utc_today() + timedelta(days=1):
        raise ValueError('date cannot be in the future')
    return parsed.isoformat()


def _week_index(d: date) -> int:
    """Monday-aligned week number (ordinal 1 = Monday), matching ISO weeks."""
    return (d.toordinal() - 1) // 7


def _consecutive_periods(periods: set[int], current: int) -> int:
    """Count consecutive periods ending at the latest of `current + 1` (clients
    ahead of UTC may check in one day early), `current`, or `current - 1` (grace)."""
    if current + 1 in periods:
        cursor = current + 1
    elif current in periods:
        cursor = current
    else:
        cursor = current - 1
    streak = 0
    while cursor in periods:
        streak += 1
        cursor -= 1
    return streak


def daily_streak(checked: set[date], today: date) -> int:
    return _consecutive_periods({d.toordinal() for d in checked}, today.toordinal())


def weekly_streak(checked: set[date], today: date) -> int:
    return _consecutive_periods({_week_index(d) for d in checked}, _week_index(today))


def _streak(habit: dict, checked: set[date], today: date) -> int:
    calc = weekly_streak if habit['frequency'] == 'weekly' else daily_streak
    return calc(checked, today)


class HabitService:
    def __init__(self, collection=None, logs_collection=None):
        if collection is None:
            db = get_db()
            self.collection = db['habits']
            self.logs = logs_collection if logs_collection is not None else db['habit_logs']
            self.collection.create_index('id', unique=True)
            self.collection.create_index('user_id')
            self.logs.create_index([('habit_id', 1), ('date', 1)], unique=True)
            self.logs.create_index('user_id')
        else:
            self.collection = collection
            self.logs = (
                logs_collection if logs_collection is not None
                else collection.database['habit_logs']
            )

    def get_all(self, user_id: str) -> list:
        habits = [strip_doc(h) for h in self.collection.find({'user_id': user_id})]
        if not habits:
            return habits
        dates_by_habit = defaultdict(set)
        for log in self.logs.find({'user_id': user_id}, {'habit_id': 1, 'date': 1, '_id': 0}):
            dates_by_habit[log['habit_id']].add(date.fromisoformat(log['date']))
        today = utc_today()
        for habit in habits:
            habit['streak'] = _streak(habit, dates_by_habit[habit['id']], today)
        return habits

    def get_one(self, user_id: str, uid: str) -> dict | None:
        habit = self.collection.find_one({'id': uid, 'user_id': user_id})
        return self._with_streak(habit) if habit else None

    def create(self, user_id: str, name: str, frequency=None) -> dict:
        habit = {
            'id': str(uuid4()),
            'user_id': user_id,
            'name': require_string(name, 'name'),
            'frequency': _validate_frequency(frequency),
            'created_at': standard_now(),
        }
        self.collection.insert_one(habit)
        habit = strip_doc(habit)
        habit['streak'] = 0
        return habit

    def update(self, user_id: str, uid: str, name=None, frequency=None) -> dict | None:
        patch = {}
        if name is not None:
            patch['name'] = require_string(name, 'name')
        if frequency is not None:
            patch['frequency'] = _validate_frequency(frequency)
        if not patch:
            return self.get_one(user_id, uid)
        habit = self.collection.find_one_and_update(
            {'id': uid, 'user_id': user_id},
            {'$set': patch},
            return_document=ReturnDocument.AFTER,
        )
        return self._with_streak(habit) if habit else None

    def delete(self, user_id: str, uid: str) -> bool:
        deleted = self.collection.delete_one({'id': uid, 'user_id': user_id}).deleted_count > 0
        if deleted:
            self.logs.delete_many({'habit_id': uid})
        return deleted

    def check(self, user_id: str, uid: str, on_date=None) -> dict | None:
        """Record a completion for a habit. Idempotent per (habit, date)."""
        habit = self.collection.find_one({'id': uid, 'user_id': user_id})
        if habit is None:
            return None
        day = _validate_date(on_date)
        try:
            self.logs.update_one(
                {'habit_id': uid, 'date': day},
                {'$set': {'user_id': user_id, 'completed': True},
                 '$setOnInsert': {'checked_at': standard_now()}},
                upsert=True,
            )
        except DuplicateKeyError:
            pass  # concurrent check for the same day already recorded it
        return self._with_streak(habit)

    def get_logs(self, user_id: str, uid: str) -> list | None:
        if self.collection.find_one({'id': uid, 'user_id': user_id}) is None:
            return None
        logs = self.logs.find({'habit_id': uid}).sort('date', 1)
        return [strip_doc(l) for l in logs]

    def _checked_dates(self, uid: str) -> set[date]:
        logs = self.logs.find({'habit_id': uid}, {'date': 1, '_id': 0})
        return {date.fromisoformat(l['date']) for l in logs}

    def _with_streak(self, habit: dict) -> dict:
        habit = strip_doc(habit)
        habit['streak'] = _streak(habit, self._checked_dates(habit['id']), utc_today())
        return habit
