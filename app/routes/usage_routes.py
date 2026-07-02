import logging
from flask import jsonify, g
from app.services.ai_ledger import AILedger
from app.utils.auth import require_auth

logger = logging.getLogger(__name__)


def register_usage_routes(app, ledger=None):
    if ledger is None:
        ledger = AILedger()

    @app.route('/api/me/usage', methods=['GET'])
    @require_auth
    def my_usage():
        try:
            return jsonify(ledger.usage(g.user_id)), 200
        except Exception:
            logger.exception('Usage backend unavailable')
            return jsonify({'error': 'Usage is temporarily unavailable'}), 503
