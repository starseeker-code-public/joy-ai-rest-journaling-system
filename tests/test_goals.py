import pytest
import mongomock

from app.routes.goal_routes import register_goal_routes
from app.services.goal_service import GoalService, _progress
from tests.conftest import register_and_login as _register_and_login


@pytest.fixture
def app(mongo, make_app):
    goal_service = GoalService(collection=mongo['goals'])
    return make_app(lambda app: register_goal_routes(app, service=goal_service))


def _create(client, headers, **overrides):
    payload = {'title': 'Learn Rust', **overrides}
    return client.post('/api/goals', json=payload, headers=headers).get_json()


# --- auth gate ---

def test_list_without_token_returns_401(client):
    assert client.get('/api/goals').status_code == 401


def test_create_without_token_returns_401(client):
    assert client.post('/api/goals', json={'title': 'X'}).status_code == 401


def test_complete_milestone_without_token_returns_401(client):
    assert client.post('/api/goals/g/milestones/m/complete').status_code == 401


# --- create ---

def test_create_returns_201_with_defaults(client, auth_headers):
    res = client.post('/api/goals', json={'title': 'Learn Rust'}, headers=auth_headers)
    assert res.status_code == 201
    data = res.get_json()
    assert data['title'] == 'Learn Rust'
    assert data['description'] == ''
    assert data['target_date'] is None
    assert data['milestones'] == []
    assert data['progress'] == 0.0
    assert 'id' in data
    assert 'created_at' in data


def test_create_with_all_fields(client, auth_headers):
    res = client.post('/api/goals', json={
        'title': 'Ship v1',
        'description': 'The big launch',
        'target_date': '2026-12-31',
        'milestones': ['design', 'build', 'launch'],
    }, headers=auth_headers)
    assert res.status_code == 201
    data = res.get_json()
    assert data['description'] == 'The big launch'
    assert data['target_date'] == '2026-12-31'
    assert [m['title'] for m in data['milestones']] == ['design', 'build', 'launch']
    assert all(m['completed'] is False for m in data['milestones'])
    assert all(m['completed_at'] is None for m in data['milestones'])
    assert all('id' in m for m in data['milestones'])
    assert data['progress'] == 0.0


def test_create_missing_title_returns_400(client, auth_headers):
    assert client.post('/api/goals', json={}, headers=auth_headers).status_code == 400


def test_create_blank_title_returns_400(client, auth_headers):
    assert client.post('/api/goals', json={'title': '  '}, headers=auth_headers).status_code == 400


def test_create_invalid_target_date_returns_400(client, auth_headers):
    assert client.post('/api/goals', json={'title': 'X', 'target_date': 'soon'}, headers=auth_headers).status_code == 400
    assert client.post('/api/goals', json={'title': 'X', 'target_date': 20261231}, headers=auth_headers).status_code == 400


def test_create_invalid_milestones_returns_400(client, auth_headers):
    assert client.post('/api/goals', json={'title': 'X', 'milestones': 'design'}, headers=auth_headers).status_code == 400
    assert client.post('/api/goals', json={'title': 'X', 'milestones': [1, 2]}, headers=auth_headers).status_code == 400
    assert client.post('/api/goals', json={'title': 'X', 'milestones': ['ok', '  ']}, headers=auth_headers).status_code == 400


def test_create_invalid_description_returns_400(client, auth_headers):
    assert client.post('/api/goals', json={'title': 'X', 'description': 42}, headers=auth_headers).status_code == 400


def test_create_non_object_json_body_returns_400(client, auth_headers):
    res = client.post('/api/goals', data='"a title"', content_type='application/json', headers=auth_headers)
    assert res.status_code == 400


# --- list / get ---

def test_list_empty(client, auth_headers):
    res = client.get('/api/goals', headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json() == []


def test_list_contains_created_goals(client, auth_headers):
    _create(client, auth_headers, title='A')
    _create(client, auth_headers, title='B')
    data = client.get('/api/goals', headers=auth_headers).get_json()
    assert {g['title'] for g in data} == {'A', 'B'}


def test_get_one_returns_goal(client, auth_headers):
    created = _create(client, auth_headers)
    res = client.get(f'/api/goals/{created["id"]}', headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()['id'] == created['id']


def test_get_one_unknown_id_returns_404(client, auth_headers):
    assert client.get('/api/goals/nonexistent', headers=auth_headers).status_code == 404


# --- update ---

def test_update_fields(client, auth_headers):
    created = _create(client, auth_headers)
    res = client.put(f'/api/goals/{created["id"]}', json={
        'title': 'New title',
        'description': 'New desc',
        'target_date': '2027-01-01',
    }, headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data['title'] == 'New title'
    assert data['description'] == 'New desc'
    assert data['target_date'] == '2027-01-01'


def test_update_partial_preserves_other_fields(client, auth_headers):
    created = _create(client, auth_headers, description='Keep me')
    res = client.put(f'/api/goals/{created["id"]}', json={'title': 'Changed'}, headers=auth_headers)
    data = res.get_json()
    assert data['title'] == 'Changed'
    assert data['description'] == 'Keep me'


def test_update_does_not_touch_milestones(client, auth_headers):
    created = _create(client, auth_headers, milestones=['a', 'b'])
    res = client.put(f'/api/goals/{created["id"]}', json={'title': 'Changed'}, headers=auth_headers)
    assert [m['title'] for m in res.get_json()['milestones']] == ['a', 'b']


def test_update_empty_body_returns_unchanged(client, auth_headers):
    created = _create(client, auth_headers)
    res = client.put(f'/api/goals/{created["id"]}', json={}, headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()['title'] == 'Learn Rust'


def test_update_can_clear_target_date_with_null(client, auth_headers):
    created = _create(client, auth_headers, target_date='2026-12-31')
    res = client.put(f'/api/goals/{created["id"]}', json={'target_date': None}, headers=auth_headers)
    assert res.status_code == 200
    assert res.get_json()['target_date'] is None


def test_target_date_must_be_strict_iso_format(client, auth_headers):
    # date.fromisoformat alone would accept these; the API must not
    assert client.post('/api/goals', json={'title': 'X', 'target_date': '20261231'}, headers=auth_headers).status_code == 400
    assert client.post('/api/goals', json={'title': 'X', 'target_date': '2026-W01-1'}, headers=auth_headers).status_code == 400


def test_update_invalid_target_date_returns_400(client, auth_headers):
    created = _create(client, auth_headers)
    assert client.put(f'/api/goals/{created["id"]}', json={'target_date': 'nope'}, headers=auth_headers).status_code == 400


def test_update_unknown_id_returns_404(client, auth_headers):
    assert client.put('/api/goals/nonexistent', json={'title': 'X'}, headers=auth_headers).status_code == 404


# --- delete ---

def test_delete_returns_204_and_gone(client, auth_headers):
    created = _create(client, auth_headers)
    assert client.delete(f'/api/goals/{created["id"]}', headers=auth_headers).status_code == 204
    assert client.get(f'/api/goals/{created["id"]}', headers=auth_headers).status_code == 404


def test_delete_unknown_id_returns_404(client, auth_headers):
    assert client.delete('/api/goals/nonexistent', headers=auth_headers).status_code == 404


# --- add milestone ---

def test_add_milestone_returns_201(client, auth_headers):
    created = _create(client, auth_headers)
    res = client.post(f'/api/goals/{created["id"]}/milestones', json={'title': 'step 1'}, headers=auth_headers)
    assert res.status_code == 201
    data = res.get_json()
    assert [m['title'] for m in data['milestones']] == ['step 1']


def test_add_milestone_missing_title_returns_400(client, auth_headers):
    created = _create(client, auth_headers)
    assert client.post(f'/api/goals/{created["id"]}/milestones', json={}, headers=auth_headers).status_code == 400


def test_add_milestone_blank_title_returns_400(client, auth_headers):
    created = _create(client, auth_headers)
    assert client.post(f'/api/goals/{created["id"]}/milestones', json={'title': ' '}, headers=auth_headers).status_code == 400


def test_add_milestone_unknown_goal_returns_404(client, auth_headers):
    assert client.post('/api/goals/nonexistent/milestones', json={'title': 'X'}, headers=auth_headers).status_code == 404


# --- complete milestone & progress ---

def test_complete_milestone_updates_progress(client, auth_headers):
    created = _create(client, auth_headers, milestones=['a', 'b', 'c', 'd'])
    mid = created['milestones'][0]['id']
    res = client.post(f'/api/goals/{created["id"]}/milestones/{mid}/complete', headers=auth_headers)
    assert res.status_code == 200
    data = res.get_json()
    done = [m for m in data['milestones'] if m['completed']]
    assert len(done) == 1
    assert done[0]['id'] == mid
    assert done[0]['completed_at'] is not None
    assert data['progress'] == 0.25


def test_completing_all_milestones_reaches_full_progress(client, auth_headers):
    created = _create(client, auth_headers, milestones=['a', 'b'])
    for m in created['milestones']:
        res = client.post(f'/api/goals/{created["id"]}/milestones/{m["id"]}/complete', headers=auth_headers)
    assert res.get_json()['progress'] == 1.0


def test_complete_milestone_is_idempotent(client, auth_headers):
    created = _create(client, auth_headers, milestones=['a'])
    mid = created['milestones'][0]['id']
    first = client.post(f'/api/goals/{created["id"]}/milestones/{mid}/complete', headers=auth_headers).get_json()
    second = client.post(f'/api/goals/{created["id"]}/milestones/{mid}/complete', headers=auth_headers)
    assert second.status_code == 200
    # completed_at must not change on repeat completion
    assert second.get_json()['milestones'][0]['completed_at'] == first['milestones'][0]['completed_at']


def test_complete_unknown_milestone_returns_404(client, auth_headers):
    created = _create(client, auth_headers, milestones=['a'])
    assert client.post(f'/api/goals/{created["id"]}/milestones/nonexistent/complete', headers=auth_headers).status_code == 404


def test_complete_milestone_unknown_goal_returns_404(client, auth_headers):
    assert client.post('/api/goals/nonexistent/milestones/m/complete', headers=auth_headers).status_code == 404


def test_progress_with_no_milestones_is_zero(client, auth_headers):
    created = _create(client, auth_headers)
    assert created['progress'] == 0.0


# --- progress math ---

def test_progress_empty():
    assert _progress([]) == 0.0


def test_progress_fraction():
    ms = [{'completed': True}, {'completed': False}, {'completed': False}]
    assert _progress(ms) == round(1 / 3, 4)


def test_progress_complete():
    assert _progress([{'completed': True}]) == 1.0


# --- ownership isolation ---

def test_user_a_cannot_list_user_b_goals(client):
    headers_a = _register_and_login(client, email='a@example.com')
    headers_b = _register_and_login(client, email='b@example.com')
    _create(client, headers_a, title='A-private')
    assert client.get('/api/goals', headers=headers_b).get_json() == []


def test_user_a_cannot_read_user_b_goal(client):
    headers_a = _register_and_login(client, email='a@example.com')
    headers_b = _register_and_login(client, email='b@example.com')
    goal = _create(client, headers_a, title='A-private')
    assert client.get(f'/api/goals/{goal["id"]}', headers=headers_b).status_code == 404


def test_user_a_cannot_update_user_b_goal(client):
    headers_a = _register_and_login(client, email='a@example.com')
    headers_b = _register_and_login(client, email='b@example.com')
    goal = _create(client, headers_a, title='A-private')
    assert client.put(f'/api/goals/{goal["id"]}', json={'title': 'hacked'}, headers=headers_b).status_code == 404


def test_user_a_cannot_delete_user_b_goal(client):
    headers_a = _register_and_login(client, email='a@example.com')
    headers_b = _register_and_login(client, email='b@example.com')
    goal = _create(client, headers_a, title='A-private')
    assert client.delete(f'/api/goals/{goal["id"]}', headers=headers_b).status_code == 404


def test_user_a_cannot_complete_user_b_milestone(client):
    headers_a = _register_and_login(client, email='a@example.com')
    headers_b = _register_and_login(client, email='b@example.com')
    goal = _create(client, headers_a, title='A-private', milestones=['a'])
    mid = goal['milestones'][0]['id']
    assert client.post(f'/api/goals/{goal["id"]}/milestones/{mid}/complete', headers=headers_b).status_code == 404


def test_user_a_cannot_add_milestone_to_user_b_goal(client):
    headers_a = _register_and_login(client, email='a@example.com')
    headers_b = _register_and_login(client, email='b@example.com')
    goal = _create(client, headers_a, title='A-private')
    assert client.post(f'/api/goals/{goal["id"]}/milestones', json={'title': 'X'}, headers=headers_b).status_code == 404


# --- service-level ---

def test_storage_persists_across_service_instances():
    coll = mongomock.MongoClient()['joy']['goals']
    s1 = GoalService(collection=coll)
    goal = s1.create('user-1', 'Persisted')
    s2 = GoalService(collection=coll)
    assert s2.get_one('user-1', goal['id']) is not None
