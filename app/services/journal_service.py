from uuid import uuid4
from pymongo import ReturnDocument
from app.utils.tools import standard_now
from app.db import get_db


def _strip(doc: dict) -> dict:
    doc = dict(doc)
    doc.pop('_id', None)
    return doc


class JournalService:
    def __init__(self, collection=None):
        if collection is None:
            self.collection = get_db()['journals']
            self.collection.create_index('id', unique=True)
        else:
            self.collection = collection

    def get_all(self) -> list:
        return [_strip(e) for e in self.collection.find()]

    def get_one(self, uid: str) -> dict | None:
        e = self.collection.find_one({'id': uid})
        return _strip(e) if e else None

    def create(self, title: str, content: str) -> dict:
        entry = {
            'id': str(uuid4()),
            'title': title,
            'content': content,
            'date': standard_now(),
        }
        self.collection.insert_one(entry)
        return _strip(entry)

    def update(self, uid: str, title: str | None = None, content: str | None = None) -> dict | None:
        patch = {}
        if title:
            patch['title'] = title
        if content:
            patch['content'] = content
        if not patch:
            return self.get_one(uid)
        patch['date'] = standard_now()
        result = self.collection.find_one_and_update(
            {'id': uid},
            {'$set': patch},
            return_document=ReturnDocument.AFTER,
        )
        return _strip(result) if result else None

    def delete(self, uid: str) -> bool:
        return self.collection.delete_one({'id': uid}).deleted_count > 0
