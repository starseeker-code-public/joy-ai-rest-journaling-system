from flask import jsonify, g
from app.services.habit_service import HabitService
from app.utils.auth import require_auth
from app.utils.tools import json_body as _json_body


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
        data = _json_body()
        if 'name' not in data:
            return jsonify({'error': 'Name required'}), 400
        try:
            habit = service.create(g.user_id, data['name'], frequency=data.get('frequency'))
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
        data = _json_body()
        try:
            res = service.update(
                g.user_id, uid,
                name=data.get('name'),
                frequency=data.get('frequency'),
            )
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        return jsonify(res) if res else (jsonify({'error': 'Not found'}), 404)

    @app.route('/api/habits/<uid>', methods=['DELETE'])
    @require_auth
    def delete_habit(uid):
        return ('', 204) if service.delete(g.user_id, uid) else (jsonify({'error': 'Not found'}), 404)

    @app.route('/api/habits/<uid>/check', methods=['POST'])
    @require_auth
    def check_habit(uid):
        # Body is optional: a bare POST checks off today.
        data = _json_body()
        try:
            res = service.check(g.user_id, uid, on_date=data.get('date'))
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        return jsonify(res) if res else (jsonify({'error': 'Not found'}), 404)

    @app.route('/api/habits/<uid>/logs', methods=['GET'])
    @require_auth
    def habit_logs(uid):
        res = service.get_logs(g.user_id, uid)
        return jsonify(res) if res is not None else (jsonify({'error': 'Not found'}), 404)
