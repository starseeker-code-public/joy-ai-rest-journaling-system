from uuid import uuid4
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from app.db import get_db
from app.utils.tools import standard_now

_ph = PasswordHasher()


def _strip(doc: dict) -> dict:
    doc = dict(doc)
    doc.pop('_id', None)
    doc.pop('password_hash', None)
    return doc


class UserService:
    def __init__(self, collection=None):
        if collection is None:
            self.collection = get_db()['users']
            self.collection.create_index('email', unique=True)
        else:
            self.collection = collection

    def register(self, email: str, password: str) -> dict | None:
        if self.collection.find_one({'email': email}):
            return None
        user = {
            'id': str(uuid4()),
            'email': email,
            'password_hash': _ph.hash(password),
            'created_at': standard_now(),
            'ai_enabled': True,
            'settings': {},
        }
        self.collection.insert_one(user)
        return _strip(user)

    def get_by_email(self, email: str) -> dict | None:
        doc = self.collection.find_one({'email': email})
        return dict(doc) if doc else None

    def verify_password(self, password_hash: str, password: str) -> bool:
        try:
            return _ph.verify(password_hash, password)
        except VerifyMismatchError:
            return False
