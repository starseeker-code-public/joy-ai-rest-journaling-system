import pytest
import mongomock
from flask import Flask
from app.routes.auth_routes import register_auth_routes
from app.services.user_service import UserService


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config['TESTING'] = True
    collection = mongomock.MongoClient()['joy']['users']
    service = UserService(collection=collection)
    register_auth_routes(app, user_service=service)
    with app.test_client() as c:
        yield c


# --- register ---

def test_register_returns_201_with_user(client):
    res = client.post('/auth/register', json={'email': 'a@example.com', 'password': 'secret123'})
    assert res.status_code == 201
    data = res.get_json()
    assert data['email'] == 'a@example.com'
    assert 'id' in data
    assert 'created_at' in data


def test_register_does_not_expose_password_hash(client):
    res = client.post('/auth/register', json={'email': 'a@example.com', 'password': 'secret123'})
    assert 'password_hash' not in res.get_json()


def test_register_duplicate_email_returns_409(client):
    client.post('/auth/register', json={'email': 'dup@example.com', 'password': 'secret'})
    res = client.post('/auth/register', json={'email': 'dup@example.com', 'password': 'other'})
    assert res.status_code == 409


def test_register_missing_email_returns_400(client):
    assert client.post('/auth/register', json={'password': 'secret'}).status_code == 400


def test_register_missing_password_returns_400(client):
    assert client.post('/auth/register', json={'email': 'a@example.com'}).status_code == 400


def test_register_empty_body_returns_400(client):
    assert client.post('/auth/register', json={}).status_code == 400


# --- password hashing ---

def test_password_is_hashed_in_db():
    coll = mongomock.MongoClient()['joy']['users']
    svc = UserService(collection=coll)
    svc.register('a@example.com', 'plaintext')
    stored = coll.find_one({'email': 'a@example.com'})
    assert stored['password_hash'] != 'plaintext'
    assert stored['password_hash'].startswith('$argon2')


def test_verify_password_correct():
    coll = mongomock.MongoClient()['joy']['users']
    svc = UserService(collection=coll)
    svc.register('a@example.com', 'correct')
    user = svc.get_by_email('a@example.com')
    assert svc.verify_password(user['password_hash'], 'correct') is True


def test_verify_password_wrong():
    coll = mongomock.MongoClient()['joy']['users']
    svc = UserService(collection=coll)
    svc.register('a@example.com', 'correct')
    user = svc.get_by_email('a@example.com')
    assert svc.verify_password(user['password_hash'], 'wrong') is False


# --- login ---

def test_login_returns_token_and_user(client):
    client.post('/auth/register', json={'email': 'a@example.com', 'password': 'secret123'})
    res = client.post('/auth/login', json={'email': 'a@example.com', 'password': 'secret123'})
    assert res.status_code == 200
    data = res.get_json()
    assert 'token' in data
    assert data['user']['email'] == 'a@example.com'
    assert 'password_hash' not in data['user']


def test_login_wrong_password_returns_401(client):
    client.post('/auth/register', json={'email': 'a@example.com', 'password': 'secret123'})
    res = client.post('/auth/login', json={'email': 'a@example.com', 'password': 'wrong'})
    assert res.status_code == 401


def test_login_unknown_email_returns_401(client):
    res = client.post('/auth/login', json={'email': 'nobody@example.com', 'password': 'whatever'})
    assert res.status_code == 401


def test_login_missing_email_returns_400(client):
    assert client.post('/auth/login', json={'password': 'secret'}).status_code == 400


def test_login_missing_password_returns_400(client):
    assert client.post('/auth/login', json={'email': 'a@example.com'}).status_code == 400


# --- logout ---

def test_logout_returns_204(client):
    assert client.post('/auth/logout').status_code == 204


# --- me ---

def test_me_with_valid_token_returns_user(client):
    client.post('/auth/register', json={'email': 'a@example.com', 'password': 'secret123'})
    token = client.post('/auth/login', json={'email': 'a@example.com', 'password': 'secret123'}).get_json()['token']
    res = client.get('/auth/me', headers={'Authorization': f'Bearer {token}'})
    assert res.status_code == 200
    data = res.get_json()
    assert data['email'] == 'a@example.com'
    assert 'password_hash' not in data


def test_me_without_token_returns_401(client):
    assert client.get('/auth/me').status_code == 401


def test_me_with_invalid_token_returns_401(client):
    res = client.get('/auth/me', headers={'Authorization': 'Bearer not.a.real.token'})
    assert res.status_code == 401


def test_me_with_malformed_auth_header_returns_401(client):
    res = client.get('/auth/me', headers={'Authorization': 'Token abc'})
    assert res.status_code == 401
