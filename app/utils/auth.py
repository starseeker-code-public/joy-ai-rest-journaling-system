from functools import wraps

from flask import g, jsonify, request

from app.utils.jwt_utils import decode_token


def get_bearer_token() -> str | None:
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        return auth[7:]
    return None


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = get_bearer_token()
        if not token:
            return jsonify({'error': 'Missing token'}), 401
        payload = decode_token(token)
        if not payload:
            return jsonify({'error': 'Invalid token'}), 401
        g.user_id = payload['sub']
        return fn(*args, **kwargs)

    return wrapper
