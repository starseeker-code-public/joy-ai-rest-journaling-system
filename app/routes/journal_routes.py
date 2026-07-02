import logging
from flask import jsonify, g, request
from app.services.journal_service import JournalService
from app.utils.auth import require_auth
from app.utils.tools import json_body
from app.utils.validators import parse_iso_date

logger = logging.getLogger(__name__)


def register_journal_routes(app, service=None, publisher=None, search_service=None):
    if service is None:
        service = JournalService(publisher=publisher)

    @app.route('/api/journals', methods=['GET'])
    @require_auth
    def list_entries():
        return jsonify(service.get_all(g.user_id)), 200

    @app.route('/api/journals', methods=['POST'])
    @require_auth
    def create_entry():
        data = json_body()
        if 'title' not in data:
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

    @app.route('/api/journals/search', methods=['GET'])
    @require_auth
    def search_entries():
        if search_service is None:
            return jsonify({'error': 'Search is not available'}), 503
        tags_param = request.args.get('tags', '')
        tags = [t for t in (t.strip() for t in tags_param.split(',')) if t] or None
        try:
            limit = int(request.args.get('limit', '20'))
        except ValueError:
            return jsonify({'error': 'limit must be a positive integer'}), 400
        if limit < 1:
            return jsonify({'error': 'limit must be a positive integer'}), 400
        try:
            date_from = request.args.get('from')
            date_to = request.args.get('to')
            if date_from:
                parse_iso_date(date_from, 'from')
            if date_to:
                parse_iso_date(date_to, 'to')
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        try:
            results = search_service.search(
                g.user_id,
                q=request.args.get('q'),
                tags=tags,
                kind=request.args.get('kind'),
                date_from=date_from,
                date_to=date_to,
                limit=limit,
            )
        except Exception:
            logger.exception('Search backend unavailable')
            return jsonify({'error': 'Search is temporarily unavailable'}), 503
        return jsonify(results), 200

    @app.route('/api/journals/<uid>', methods=['GET'])
    @require_auth
    def get_entry(uid):
        res = service.get_one(g.user_id, uid)
        return jsonify(res) if res else (jsonify({'error': 'Not found'}), 404)

    @app.route('/api/journals/<uid>', methods=['PUT'])
    @require_auth
    def update_entry(uid):
        data = json_body()
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

    @app.route('/api/journals/<uid>/sentiment', methods=['GET'])
    @require_auth
    def get_sentiment(uid):
        entry = service.get_one(g.user_id, uid)
        if entry is None:
            return jsonify({'error': 'Not found'}), 404
        sentiment = (entry.get('ai') or {}).get('sentiment')
        if sentiment is None:
            return jsonify({'status': 'pending'}), 202, {'Retry-After': '2'}
        return jsonify(sentiment), 200
