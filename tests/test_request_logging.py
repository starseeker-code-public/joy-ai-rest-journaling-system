import json
import logging

import pytest
from flask import Flask, jsonify

from app.utils.logging_config import configure_logging
from app.utils.request_logging import register_request_logging


@pytest.fixture
def app():
    app = Flask('test')
    app.config['TESTING'] = True
    register_request_logging(app)

    @app.route('/ping')
    def ping():
        return jsonify({'ok': True}), 200

    return app


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


def test_response_carries_request_id(client):
    res = client.get('/ping')
    assert res.headers.get('X-Request-ID')


def test_inbound_request_id_is_honored(client):
    res = client.get('/ping', headers={'X-Request-ID': 'trace-me-123'})
    assert res.headers['X-Request-ID'] == 'trace-me-123'


def test_request_ids_are_unique_per_request(client):
    first = client.get('/ping').headers['X-Request-ID']
    second = client.get('/ping').headers['X-Request-ID']
    assert first != second


def test_access_log_line_has_request_fields(client, monkeypatch, capsys):
    # Route structlog through stdlib in JSON mode so the line is parseable
    monkeypatch.setenv('LOG_FORMAT', 'json')
    configure_logging()
    client.get('/ping', headers={'X-Request-ID': 'rid-1'})
    line = capsys.readouterr().err.strip().splitlines()[-1]
    parsed = json.loads(line)
    assert parsed['event'] == 'request'
    assert parsed['request_id'] == 'rid-1'
    assert parsed['method'] == 'GET'
    assert parsed['path'] == '/ping'
    assert parsed['status'] == 200
    assert parsed['duration_ms'] >= 0


def test_json_log_format(monkeypatch, capsys):
    monkeypatch.setenv('LOG_FORMAT', 'json')
    configure_logging()
    logging.getLogger('joy.test').info('hello world')
    line = capsys.readouterr().err.strip().splitlines()[-1]
    parsed = json.loads(line)
    assert parsed['event'] == 'hello world'
    assert parsed['logger'] == 'joy.test'
    assert parsed['level'] == 'info'
    assert 'timestamp' in parsed


def test_console_log_format(monkeypatch, capsys):
    monkeypatch.setenv('LOG_FORMAT', 'console')
    configure_logging()
    logging.getLogger('joy.test').info('plain line')
    line = capsys.readouterr().err.strip()
    assert 'plain line' in line
    with pytest.raises(json.JSONDecodeError):
        json.loads(line.splitlines()[-1])


def test_malformed_inbound_request_id_is_replaced(client):
    res = client.get('/ping', headers={'X-Request-ID': 'bad id \x1b[2J' + 'x' * 200})
    rid = res.headers['X-Request-ID']
    assert rid != 'bad id'
    assert len(rid) == 36  # a fresh uuid4


def test_overlong_request_id_is_replaced(client):
    res = client.get('/ping', headers={'X-Request-ID': 'a' * 300})
    assert len(res.headers['X-Request-ID']) == 36
