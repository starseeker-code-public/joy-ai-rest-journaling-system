from flask import jsonify, g
from app.services.goal_service import GoalService, UNSET
from app.utils.auth import require_auth
from app.utils.metrics import GOALS_CREATED
from app.utils.tools import json_body


def register_goal_routes(app, service=None):
    if service is None:
        service = GoalService()

    @app.route('/api/goals', methods=['GET'])
    @require_auth
    def list_goals():
        return jsonify(service.get_all(g.user_id)), 200

    @app.route('/api/goals', methods=['POST'])
    @require_auth
    def create_goal():
        data = json_body()
        if 'title' not in data:
            return jsonify({'error': 'Title required'}), 400
        try:
            goal = service.create(
                g.user_id,
                data['title'],
                description=data.get('description'),
                target_date=data.get('target_date'),
                milestones=data.get('milestones'),
            )
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        GOALS_CREATED.inc()
        return jsonify(goal), 201

    @app.route('/api/goals/<uid>', methods=['GET'])
    @require_auth
    def get_goal(uid):
        res = service.get_one(g.user_id, uid)
        return jsonify(res) if res else (jsonify({'error': 'Not found'}), 404)

    @app.route('/api/goals/<uid>', methods=['PUT'])
    @require_auth
    def update_goal(uid):
        data = json_body()
        try:
            res = service.update(
                g.user_id, uid,
                title=data.get('title'),
                description=data.get('description'),
                # Presence of the key matters: an explicit null clears the date
                target_date=data['target_date'] if 'target_date' in data else UNSET,
            )
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        return jsonify(res) if res else (jsonify({'error': 'Not found'}), 404)

    @app.route('/api/goals/<uid>', methods=['DELETE'])
    @require_auth
    def delete_goal(uid):
        return ('', 204) if service.delete(g.user_id, uid) else (jsonify({'error': 'Not found'}), 404)

    @app.route('/api/goals/<uid>/milestones', methods=['POST'])
    @require_auth
    def add_milestone(uid):
        data = json_body()
        if 'title' not in data:
            return jsonify({'error': 'Title required'}), 400
        try:
            res = service.add_milestone(g.user_id, uid, data['title'])
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        return (jsonify(res), 201) if res else (jsonify({'error': 'Not found'}), 404)

    @app.route('/api/goals/<uid>/milestones/<mid>/complete', methods=['POST'])
    @require_auth
    def complete_milestone(uid, mid):
        res = service.complete_milestone(g.user_id, uid, mid)
        return jsonify(res) if res else (jsonify({'error': 'Not found'}), 404)
