from flask import Flask

from app.routes.health_routes import register_health_routes


def _client(checks):
    app = Flask('test')
    app.config['TESTING'] = True
    register_health_routes(app, checks=checks)
    return app.test_client()


def test_health_all_healthy():
    client = _client({'mongo': lambda: None, 'redis': lambda: None})
    res = client.get('/health')
    assert res.status_code == 200
    body = res.get_json()
    assert body['status'] == 'healthy'
    assert body['services'] == {'mongo': 'healthy', 'redis': 'healthy'}


def test_health_degraded_when_a_check_fails():
    def boom():
        raise ConnectionError('down')

    client = _client({'mongo': lambda: None, 'clickhouse': boom})
    body = client.get('/health').get_json()
    assert body['status'] == 'degraded'
    assert body['services']['mongo'] == 'healthy'
    assert body['services']['clickhouse'] == 'unhealthy'


def test_health_with_no_checks_is_healthy():
    client = _client({})
    body = client.get('/health').get_json()
    assert body == {'status': 'healthy', 'services': {}}
