from flask import request, jsonify
from app.services.user_service import UserService


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
