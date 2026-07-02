"""Shared test scaffolding: mongomock-backed Flask app factory and auth helpers."""
import pytest
import mongomock
from flask import Flask

from app.routes.auth_routes import register_auth_routes
from app.services.user_service import UserService
from app.utils.rate_limiter import RateLimiter


@pytest.fixture
def mongo():
    return mongomock.MongoClient()['joy']


@pytest.fixture
def make_app(mongo):
    """Factory producing a TESTING app with auth routes plus any domain routes."""
    def factory(*register_fns):
        app = Flask('test')
        app.config['TESTING'] = True
        user_service = UserService(collection=mongo['users'])
        permissive = RateLimiter(max_attempts=1000, window_seconds=60)
        register_auth_routes(app, user_service=user_service, login_limiter=permissive)
        for register in register_fns:
            register(app)
        return app
    return factory


@pytest.fixture
def client(app):
    """Test client for the module's `app` fixture."""
    with app.test_client() as c:
        yield c


@pytest.fixture
def auth_headers(client):
    return register_and_login(client)


def register_and_login(client, email='a@example.com', password='secret123'):
    client.post('/auth/register', json={'email': email, 'password': password})
    token = client.post('/auth/login', json={'email': email, 'password': password}).get_json()['token']
    return {'Authorization': f'Bearer {token}'}
