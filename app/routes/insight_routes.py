import logging
from flask import jsonify, g
from app.services.insight_service import InsightService
from app.utils.auth import require_auth

logger = logging.getLogger(__name__)


def register_insight_routes(app, service=None):
    if service is None:
        service = InsightService()

    @app.route('/api/insights', methods=['GET'])
    @require_auth
    def list_insights():
        return jsonify(service.get_all(g.user_id)), 200
