from flask import jsonify, request

from app.services.user_service import InvalidCredentials, UserService
from app.utils.auth import get_bearer_token
from app.utils.jwt_utils import decode_token, issue_token
from app.utils.rate_limiter import RateLimiter
from app.utils.tools import strip_doc


def register_auth_routes(app, user_service=None, login_limiter=None):
    if user_service is None:
        user_service = UserService()
    if login_limiter is None:
        login_limiter = RateLimiter(max_attempts=5, window_seconds=15 * 60)

    @app.route('/auth/register', methods=['POST'])
    def register():
        data = request.json
        if not data or not data.get('email') or not data.get('password'):
            return jsonify({'error': 'Email and password required'}), 400
        try:
            user = user_service.register(data['email'], data['password'])
        except InvalidCredentials as e:
            return jsonify({'error': str(e)}), 400
        if user is None:
            return jsonify({'error': 'Email already registered'}), 409
        return jsonify(user), 201

    @app.route('/auth/login', methods=['POST'])
    def login():
        ip = request.remote_addr or 'unknown'
        if not login_limiter.allow(f'login:{ip}'):
            return jsonify({'error': 'Too many attempts, try again later'}), 429
        data = request.json
        if not data or not data.get('email') or not data.get('password'):
            return jsonify({'error': 'Email and password required'}), 400
        user = user_service.get_by_email(data['email'])
        if not user or not user_service.verify_password(user['password_hash'], data['password']):
            return jsonify({'error': 'Invalid credentials'}), 401
        token = issue_token(user['id'])
        return jsonify({'token': token, 'user': strip_doc(user, 'password_hash')}), 200

    @app.route('/auth/logout', methods=['POST'])
    def logout():
        return ('', 204)

    @app.route('/auth/me', methods=['GET'])
    def me():
        token = get_bearer_token()
        if not token:
            return jsonify({'error': 'Missing token'}), 401
        payload = decode_token(token)
        if not payload:
            return jsonify({'error': 'Invalid token'}), 401
        user = user_service.get_by_id(payload['sub'])
        if not user:
            return jsonify({'error': 'User not found'}), 401
        return jsonify(user), 200
