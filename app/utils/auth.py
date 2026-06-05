from functools import wraps
from flask import request, jsonify, g
from app.utils.jwt_utils import decode_token


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return jsonify({'error': 'Missing token'}), 401
        payload = decode_token(auth[7:])
        if not payload:
            return jsonify({'error': 'Invalid token'}), 401
        g.user_id = payload['sub']
        return fn(*args, **kwargs)
    return wrapper
