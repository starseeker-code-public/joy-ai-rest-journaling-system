from flask import request, jsonify, g
from app.services.journal_service import JournalService
from app.utils.auth import require_auth


def register_journal_routes(app, service=None):
    if service is None:
        service = JournalService()

    @app.route('/api/journals', methods=['GET'])
    @require_auth
    def list_entries():
        return jsonify(service.get_all(g.user_id)), 200

    @app.route('/api/journals', methods=['POST'])
    @require_auth
    def create_entry():
        data = request.json
        if not data or 'title' not in data:
            return jsonify({'error': 'Title required'}), 400
        try:
            entry = service.create(
                g.user_id,
                data['title'],
                data.get('content', ''),
                mood=data.get('mood'),
                tags=data.get('tags'),
                kind=data.get('kind'),
            )
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        return jsonify(entry), 201

    @app.route('/api/journals/<uid>', methods=['GET'])
    @require_auth
    def get_entry(uid):
        res = service.get_one(g.user_id, uid)
        return jsonify(res) if res else (jsonify({'error': 'Not found'}), 404)

    @app.route('/api/journals/<uid>', methods=['PUT'])
    @require_auth
    def update_entry(uid):
        data = request.json or {}
        try:
            res = service.update(
                g.user_id, uid,
                title=data.get('title'),
                content=data.get('content'),
                mood=data.get('mood'),
                tags=data.get('tags'),
                kind=data.get('kind'),
            )
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        return jsonify(res) if res else (jsonify({'error': 'Not found'}), 404)

    @app.route('/api/journals/<uid>', methods=['DELETE'])
    @require_auth
    def delete_entry(uid):
        return ('', 204) if service.delete(g.user_id, uid) else (jsonify({'error': 'Not found'}), 404)
