from flask import request, jsonify
from app.services.journal_service import JournalService

def register_journal_routes(app, service=None):
    if service is None:
        service = JournalService()

    @app.route('/api/journals', methods=['GET'])
    def list_entries():
        return jsonify(service.get_all()), 200

    @app.route('/api/journals', methods=['POST'])
    def create_entry():
        data = request.json
        if not data or 'title' not in data: return jsonify({'error': 'Title required'}), 400
        return jsonify(service.create(data['title'], data.get('content', ''))), 201

    @app.route('/api/journals/<uid>', methods=['GET'])
    def get_entry(uid):
        res = service.get_one(uid)
        return jsonify(res) if res else (jsonify({'error': 'Not found'}), 404)

    @app.route('/api/journals/<uid>', methods=['PUT'])
    def update_entry(uid):
        data = request.json
        res = service.update(uid, data.get('title'), data.get('content'))
        return jsonify(res) if res else (jsonify({'error': 'Not found'}), 404)

    @app.route('/api/journals/<uid>', methods=['DELETE'])
    def delete_entry(uid):
        return ('', 204) if service.delete(uid) else (jsonify({'error': 'Not found'}), 404)

