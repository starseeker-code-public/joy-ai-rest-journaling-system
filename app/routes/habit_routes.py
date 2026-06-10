from flask import request, jsonify, g
from app.services.habit_service import HabitService
from app.utils.auth import require_auth


def register_habit_routes(app, service=None):
    if service is None:
        service = HabitService()

    @app.route('/api/habits', methods=['GET'])
    @require_auth
    def list_habits():
        return jsonify(service.get_all(g.user_id)), 200

    @app.route('/api/habits', methods=['POST'])
    @require_auth
    def create_habit():
        data = request.json
        if not data or 'name' not in data:
            return jsonify({'error': 'Name required'}), 400
        try:
            habit = service.create(
                g.user_id,
                data['name'],
                target_freq=data.get('target_freq'),
            )
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        return jsonify(habit), 201

    @app.route('/api/habits/<uid>', methods=['GET'])
    @require_auth
    def get_habit(uid):
        res = service.get_one(g.user_id, uid)
        return jsonify(res) if res else (jsonify({'error': 'Not found'}), 404)

    @app.route('/api/habits/<uid>', methods=['PUT'])
    @require_auth
    def update_habit(uid):
        data = request.json or {}
        try:
            res = service.update(
                g.user_id, uid,
                name=data.get('name'),
                target_freq=data.get('target_freq'),
            )
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        return jsonify(res) if res else (jsonify({'error': 'Not found'}), 404)

    @app.route('/api/habits/<uid>', methods=['DELETE'])
    @require_auth
    def delete_habit(uid):
        return ('', 204) if service.delete(g.user_id, uid) else (jsonify({'error': 'Not found'}), 404)
