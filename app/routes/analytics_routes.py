import logging
from flask import jsonify, g, request
from app.services.analytics_service import AnalyticsService
from app.utils.auth import require_auth

logger = logging.getLogger(__name__)


def _int_param(name: str, default: int, maximum: int) -> int:
    raw = request.args.get(name, str(default))
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f'{name} must be an integer')
    if value < 1 or value > maximum:
        raise ValueError(f'{name} must be between 1 and {maximum}')
    return value


def register_analytics_routes(app, service=None):
    if service is None:
        service = AnalyticsService()

    @app.route('/api/analytics/mood-trend', methods=['GET'])
    @require_auth
    def mood_trend():
        try:
            days = _int_param('days', default=30, maximum=365)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        try:
            trend = service.mood_trend(g.user_id, days=days)
        except Exception:
            logger.exception('Analytics backend unavailable')
            return jsonify({'error': 'Analytics is temporarily unavailable'}), 503
        return jsonify(trend), 200

    @app.route('/api/analytics/tag-frequency', methods=['GET'])
    @require_auth
    def tag_frequency():
        try:
            limit = _int_param('limit', default=10, maximum=100)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        try:
            tags = service.tag_frequency(g.user_id, limit=limit)
        except Exception:
            logger.exception('Analytics backend unavailable')
            return jsonify({'error': 'Analytics is temporarily unavailable'}), 503
        return jsonify(tags), 200
