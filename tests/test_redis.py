import time

import fakeredis
import pytest
import mongomock

from app.routes.auth_routes import register_auth_routes
from app.services.user_service import UserService
from app.utils.redis_rate_limiter import RedisRateLimiter
from app.utils.user_cache import UserCache
from tests.conftest import register_and_login as _register_and_login


@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis()


# --- RedisRateLimiter ---

def test_allows_up_to_max_attempts(redis_client):
    limiter = RedisRateLimiter(max_attempts=3, window_seconds=60, client=redis_client)
    assert [limiter.allow('login:1.2.3.4') for _ in range(4)] == [True, True, True, False]


def test_keys_are_independent(redis_client):
    limiter = RedisRateLimiter(max_attempts=1, window_seconds=60, client=redis_client)
    assert limiter.allow('login:a') is True
    assert limiter.allow('login:b') is True
    assert limiter.allow('login:a') is False


def test_state_is_shared_across_instances(redis_client):
    first = RedisRateLimiter(max_attempts=2, window_seconds=60, client=redis_client)
    second = RedisRateLimiter(max_attempts=2, window_seconds=60, client=redis_client)
    assert first.allow('login:x') is True
    assert second.allow('login:x') is True
    assert first.allow('login:x') is False


def test_window_expires(redis_client):
    limiter = RedisRateLimiter(max_attempts=1, window_seconds=1, client=redis_client)
    assert limiter.allow('login:x') is True
    assert limiter.allow('login:x') is False
    time.sleep(1.1)
    assert limiter.allow('login:x') is True


def test_window_does_not_slide_on_repeat_attempts(redis_client):
    limiter = RedisRateLimiter(max_attempts=1, window_seconds=60, client=redis_client)
    limiter.allow('login:x')
    ttl_first = redis_client.ttl('ratelimit:login:x')
    limiter.allow('login:x')
    assert redis_client.ttl('ratelimit:login:x') <= ttl_first


def test_fails_open_when_redis_down():
    class Exploding:
        def pipeline(self):
            raise ConnectionError('redis down')

    limiter = RedisRateLimiter(max_attempts=1, window_seconds=60, client=Exploding())
    assert limiter.allow('login:x') is True
    assert limiter.allow('login:x') is True


# --- UserCache ---

def test_cache_roundtrip(redis_client):
    cache = UserCache(client=redis_client, ttl_seconds=60)
    assert cache.get('u1') is None
    cache.set('u1', {'id': 'u1', 'email': 'a@example.com'})
    assert cache.get('u1') == {'id': 'u1', 'email': 'a@example.com'}


def test_cache_sets_ttl(redis_client):
    cache = UserCache(client=redis_client, ttl_seconds=60)
    cache.set('u1', {'id': 'u1'})
    assert 0 < redis_client.ttl('user:u1') <= 60


def test_cache_fails_open():
    class Exploding:
        def get(self, key):
            raise ConnectionError('redis down')

        def set(self, *a, **k):
            raise ConnectionError('redis down')

    cache = UserCache(client=Exploding())
    assert cache.get('u1') is None
    cache.set('u1', {'id': 'u1'})  # must not raise


# --- /auth/me caching integration ---

class CountingUserService(UserService):
    def __init__(self, collection):
        super().__init__(collection=collection)
        self.lookups = 0

    def get_by_id(self, user_id):
        self.lookups += 1
        return super().get_by_id(user_id)


@pytest.fixture
def app(redis_client):
    from flask import Flask
    mongo = mongomock.MongoClient()['joy']
    app = Flask('test')
    app.config['TESTING'] = True
    users = CountingUserService(mongo['users'])
    register_auth_routes(
        app,
        user_service=users,
        login_limiter=RedisRateLimiter(max_attempts=1000, window_seconds=60, client=redis_client),
        user_cache=UserCache(client=redis_client, ttl_seconds=60),
    )
    app.config['_users'] = users
    return app


def test_me_is_cached(client, app, auth_headers):
    users = app.config['_users']
    first = client.get('/auth/me', headers=auth_headers)
    lookups_after_first = users.lookups
    second = client.get('/auth/me', headers=auth_headers)
    assert first.get_json() == second.get_json()
    assert users.lookups == lookups_after_first  # served from cache
    assert lookups_after_first >= 1


def test_login_rate_limited_via_redis(redis_client):
    from flask import Flask
    mongo = mongomock.MongoClient()['joy']
    app = Flask('test')
    app.config['TESTING'] = True
    register_auth_routes(
        app,
        user_service=UserService(collection=mongo['users']),
        login_limiter=RedisRateLimiter(max_attempts=2, window_seconds=60, client=redis_client),
    )
    with app.test_client() as c:
        c.post('/auth/register', json={'email': 'a@example.com', 'password': 'secret123'})
        creds = {'email': 'a@example.com', 'password': 'wrong-pass'}
        assert c.post('/auth/login', json=creds).status_code == 401
        assert c.post('/auth/login', json=creds).status_code == 401
        assert c.post('/auth/login', json=creds).status_code == 429
