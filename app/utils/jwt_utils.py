import os
from datetime import UTC, datetime, timedelta

import jwt

ALGORITHM = 'HS256'
EXPIRY_DAYS = 30


def _secret() -> str:
    return os.getenv('SECRET_KEY', 'dev-secret-key-change-me-in-production-12345')


def issue_token(user_id: str) -> str:
    now = datetime.now(UTC)
    payload = {
        'sub': user_id,
        'iat': now,
        'exp': now + timedelta(days=EXPIRY_DAYS),
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, _secret(), algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
