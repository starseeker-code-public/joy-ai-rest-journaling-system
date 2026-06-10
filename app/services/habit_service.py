from datetime import datetime, timezone
from uuid import uuid4
from pymongo import ReturnDocument
from app.utils.tools import standard_now, strip_doc
from app.db import get_db

VALID_FREQUENCIES = {'daily', 'weekly'}


def _today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _validate_date(date_str):
    if not isinstance(date_str, str):
        raise ValueError('date must be a string in YYYY-MM-DD format')
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError as e:
        raise ValueError('date must be in YYYY-MM-DD format') from e
    return date_str


def _validate_name(name):
    if not isinstance(name, str) or not name.strip():
        raise ValueError('name must be a non-empty string')
    return name.strip()


def _validate_target_freq(freq):
    if freq is None:
        return 'daily'
    if freq not in VALID_FREQUENCIES:
        raise ValueError(f'target_freq must be one of {sorted(VALID_FREQUENCIES)}')
    return freq


class HabitService:
    def __init__(self, collection=None):
        if collection is None:
            self.collection = get_db()['habits']
            self.collection.create_index('id', unique=True)
            self.collection.create_index('user_id')
        else:
            self.collection = collection

    def create(self, user_id: str, name: str, target_freq: str | None = None) -> dict:
        entry = {
            'id': str(uuid4()),
            'user_id': user_id,
            'name': _validate_name(name),
            'target_freq': _validate_target_freq(target_freq),
            'created_at': standard_now(),
            'completions': [],
        }
        self.collection.insert_one(entry)
        return strip_doc(entry)

    def get_all(self, user_id: str) -> list:
        return [strip_doc(h) for h in self.collection.find({'user_id': user_id})]

    def get_one(self, user_id: str, uid: str) -> dict | None:
        h = self.collection.find_one({'id': uid, 'user_id': user_id})
        return strip_doc(h) if h else None

    def update(
        self,
        user_id: str,
        uid: str,
        name: str | None = None,
        target_freq: str | None = None,
    ) -> dict | None:
        patch = {}
        if name is not None:
            patch['name'] = _validate_name(name)
        if target_freq is not None:
            patch['target_freq'] = _validate_target_freq(target_freq)
        if not patch:
            return self.get_one(user_id, uid)
        result = self.collection.find_one_and_update(
            {'id': uid, 'user_id': user_id},
            {'$set': patch},
            return_document=ReturnDocument.AFTER,
        )
        return strip_doc(result) if result else None

    def delete(self, user_id: str, uid: str) -> bool:
        return self.collection.delete_one({'id': uid, 'user_id': user_id}).deleted_count > 0

    def check(self, user_id: str, uid: str, date: str | None = None) -> dict | None:
        """Record a completion on the given date (defaults to today UTC).

        Idempotent on the same date — adding the same date twice is a no-op.
        Returns the updated entry or None if not found / not owned.
        """
        date = _validate_date(date) if date is not None else _today_utc()
        result = self.collection.find_one_and_update(
            {'id': uid, 'user_id': user_id},
            {'$addToSet': {'completions': date}},
            return_document=ReturnDocument.AFTER,
        )
        return strip_doc(result) if result else None
