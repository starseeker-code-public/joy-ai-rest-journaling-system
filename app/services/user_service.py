import re
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.db import get_db
from app.utils.tools import standard_now, strip_doc

_ph = PasswordHasher()

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
MIN_PASSWORD_LENGTH = 8


class InvalidCredentials(ValueError):
    """Raised when registration input fails format/length validation."""


def _validate_email(email) -> str:
    if not isinstance(email, str) or not EMAIL_RE.match(email):
        raise InvalidCredentials('Invalid email format')
    return email


def _validate_password(password) -> str:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise InvalidCredentials(f'Password must be at least {MIN_PASSWORD_LENGTH} characters')
    return password


class UserService:
    def __init__(self, collection=None):
        if collection is None:
            self.collection = get_db()['users']
            self.collection.create_index('email', unique=True)
        else:
            self.collection = collection

    def register(self, email: str, password: str) -> dict | None:
        _validate_email(email)
        _validate_password(password)
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
        return strip_doc(user, 'password_hash')

    def get_by_email(self, email: str) -> dict | None:
        """Returns the raw user doc (includes password_hash). Use for login."""
        doc = self.collection.find_one({'email': email})
        return dict(doc) if doc else None

    def get_by_id(self, user_id: str) -> dict | None:
        """Returns the safe user doc (no password_hash). Use for /me, current_user."""
        doc = self.collection.find_one({'id': user_id})
        return strip_doc(doc, 'password_hash') if doc else None

    def verify_password(self, password_hash: str, password: str) -> bool:
        try:
            return _ph.verify(password_hash, password)
        except VerifyMismatchError:
            return False
