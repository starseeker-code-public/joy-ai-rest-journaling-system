from flask import request, jsonify
from app.services.user_service import UserService
from app.utils.jwt_utils import issue_token, decode_token


def _safe(user: dict) -> dict:
    u = dict(user)
    u.pop('_id', None)
    u.pop('password_hash', None)
    return u


def _bearer_token(req) -> str | None:
    auth = req.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        return auth[7:]
    return None


def register_auth_routes(app, user_service=None):
    if user_service is None:
        user_service = UserService()

    @app.route('/auth/register', methods=['POST'])
    def register():
        data = request.json
        if not data or not data.get('email') or not data.get('password'):
            return jsonify({'error': 'Email and password required'}), 400
        user = user_service.register(data['email'], data['password'])
        if user is None:
            return jsonify({'error': 'Email already registered'}), 409
        return jsonify(user), 201

    @app.route('/auth/login', methods=['POST'])
    def login():
        data = request.json
        if not data or not data.get('email') or not data.get('password'):
            return jsonify({'error': 'Email and password required'}), 400
        user = user_service.get_by_email(data['email'])
        if not user or not user_service.verify_password(user['password_hash'], data['password']):
            return jsonify({'error': 'Invalid credentials'}), 401
        token = issue_token(user['id'])
        return jsonify({'token': token, 'user': _safe(user)}), 200

    @app.route('/auth/logout', methods=['POST'])
    def logout():
        return ('', 204)

    @app.route('/auth/me', methods=['GET'])
    def me():
        token = _bearer_token(request)
        if not token:
            return jsonify({'error': 'Missing token'}), 401
        payload = decode_token(token)
        if not payload:
            return jsonify({'error': 'Invalid token'}), 401
        user = user_service.get_by_id(payload['sub'])
        if not user:
            return jsonify({'error': 'User not found'}), 401
        return jsonify(user), 200
