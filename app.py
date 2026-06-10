import os
from dotenv import load_dotenv

load_dotenv()

from flask import Flask, jsonify
from app.routes.journal_routes import register_journal_routes
from app.routes.auth_routes import register_auth_routes

DEFAULT_SECRET_KEY = 'dev-secret-key-change-me-in-production-12345'


def _is_debug() -> bool:
    return os.getenv('DEBUG', 'True').lower() in ('true', '1', 't')


def _check_secret_key() -> None:
    if _is_debug():
        return
    secret = os.getenv('SECRET_KEY')
    if not secret or secret == DEFAULT_SECRET_KEY:
        raise RuntimeError(
            'SECRET_KEY must be set to a non-default value when DEBUG is disabled. '
            'Generate a strong key (>= 32 bytes) and set it via the environment.'
        )


def create_app() -> Flask:
    _check_secret_key()
    app = Flask(__name__)
    register_journal_routes(app)
    register_auth_routes(app)

    @app.route('/health', methods=['GET'])
    def health():
        return jsonify({'status': 'healthy'}), 200

    return app


app = create_app()


if __name__ == '__main__':
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', 5000))
    app.run(host=host, port=port, debug=_is_debug())
