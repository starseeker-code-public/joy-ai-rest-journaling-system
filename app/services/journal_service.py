import logging
from uuid import uuid4
from pymongo import ReturnDocument
from app.utils.tools import standard_now, strip_doc
from app.utils.validators import require_string
from app.utils.events import JOURNAL_CREATED
from app.db import get_db

logger = logging.getLogger(__name__)

VALID_KINDS = {'text', 'voice', 'photo', 'summary'}


def _validate_mood(mood):
    if mood is None:
        return None
    if isinstance(mood, bool) or not isinstance(mood, int):
        raise ValueError('mood must be an integer between 1 and 10')
    if mood < 1 or mood > 10:
        raise ValueError('mood must be an integer between 1 and 10')
    return mood


def _validate_tags(tags):
    if tags is None:
        return []
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        raise ValueError('tags must be a list of strings')
    return tags


def _validate_kind(kind):
    if kind is None:
        return 'text'
    if kind not in VALID_KINDS:
        raise ValueError(f'kind must be one of {sorted(VALID_KINDS)}')
    return kind


class JournalService:
    def __init__(self, collection=None, publisher=None):
        if collection is None:
            self.collection = get_db()['journals']
            self.collection.create_index('id', unique=True)
            self.collection.create_index('user_id')
        else:
            self.collection = collection
        self.publisher = publisher

    def get_all(self, user_id: str) -> list:
        return [strip_doc(e) for e in self.collection.find({'user_id': user_id})]

    def get_one(self, user_id: str, uid: str) -> dict | None:
        e = self.collection.find_one({'id': uid, 'user_id': user_id})
        return strip_doc(e) if e else None

    def create(
        self,
        user_id: str,
        title: str,
        content: str,
        mood=None,
        tags=None,
        kind=None,
    ) -> dict:
        entry = {
            'id': str(uuid4()),
            'user_id': user_id,
            'title': require_string(title, 'title'),
            'content': content,
            'date': standard_now(),
            'mood': _validate_mood(mood),
            'tags': _validate_tags(tags),
            'kind': _validate_kind(kind),
            'ai': {},
        }
        self.collection.insert_one(entry)
        result = strip_doc(entry)
        self._publish(JOURNAL_CREATED, result)
        return result

    def _publish(self, routing_key: str, payload: dict) -> None:
        if self.publisher is None:
            return
        try:
            self.publisher.publish(routing_key, payload)
        except Exception:
            logger.exception('Failed to publish %s event', routing_key)

    def update(
        self,
        user_id: str,
        uid: str,
        title: str | None = None,
        content: str | None = None,
        mood=None,
        tags=None,
        kind=None,
    ) -> dict | None:
        patch = {}
        if title is not None:
            patch['title'] = require_string(title, 'title')
        if content is not None:
            patch['content'] = content
        if mood is not None:
            patch['mood'] = _validate_mood(mood)
        if tags is not None:
            patch['tags'] = _validate_tags(tags)
        if kind is not None:
            patch['kind'] = _validate_kind(kind)
        if not patch:
            return self.get_one(user_id, uid)
        patch['date'] = standard_now()
        result = self.collection.find_one_and_update(
            {'id': uid, 'user_id': user_id},
            {'$set': patch},
            return_document=ReturnDocument.AFTER,
        )
        return strip_doc(result) if result else None

    def delete(self, user_id: str, uid: str) -> bool:
        return self.collection.delete_one({'id': uid, 'user_id': user_id}).deleted_count > 0

    def set_sentiment(
        self,
        user_id: str,
        uid: str,
        sentiment: dict,
    ) -> dict | None:
        """Persist a sentiment result to entry.ai.sentiment. Returns updated entry or None."""
        enriched = dict(sentiment)
        enriched['analyzed_at'] = standard_now()
        result = self.collection.find_one_and_update(
            {'id': uid, 'user_id': user_id},
            {'$set': {'ai.sentiment': enriched}},
            return_document=ReturnDocument.AFTER,
        )
        return strip_doc(result) if result else None
