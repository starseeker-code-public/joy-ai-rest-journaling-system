import pytest
import mongomock
from app.services.habit_service import HabitService, VALID_FREQUENCIES


@pytest.fixture
def service():
    coll = mongomock.MongoClient()['joy']['habits']
    return HabitService(collection=coll)


# --- creation: happy path ---

def test_create_returns_entry_with_all_fields(service):
    habit = service.create('user-1', 'Meditate', target_freq='daily')
    assert habit['id']
    assert habit['user_id'] == 'user-1'
    assert habit['name'] == 'Meditate'
    assert habit['target_freq'] == 'daily'
    assert 'created_at' in habit


def test_create_strips_whitespace_from_name(service):
    habit = service.create('user-1', '  Read books  ')
    assert habit['name'] == 'Read books'


def test_create_defaults_target_freq_to_daily(service):
    habit = service.create('user-1', 'Walk')
    assert habit['target_freq'] == 'daily'


def test_create_accepts_weekly(service):
    habit = service.create('user-1', 'Long run', target_freq='weekly')
    assert habit['target_freq'] == 'weekly'


def test_create_persists_to_collection(service):
    habit = service.create('user-1', 'Stretch')
    stored = service.collection.find_one({'id': habit['id']})
    assert stored is not None
    assert stored['user_id'] == 'user-1'
    assert stored['name'] == 'Stretch'


def test_create_returns_no_internal_id(service):
    habit = service.create('user-1', 'Stretch')
    assert '_id' not in habit


# --- creation: validation ---

def test_create_empty_name_raises(service):
    with pytest.raises(ValueError, match='name'):
        service.create('user-1', '')


def test_create_whitespace_only_name_raises(service):
    with pytest.raises(ValueError, match='name'):
        service.create('user-1', '   ')


def test_create_non_string_name_raises(service):
    with pytest.raises(ValueError, match='name'):
        service.create('user-1', 123)


def test_create_invalid_target_freq_raises(service):
    with pytest.raises(ValueError, match='target_freq'):
        service.create('user-1', 'Read', target_freq='hourly')


# --- ownership ---

def test_create_preserves_distinct_user_ids(service):
    a = service.create('user-a', 'Habit A')
    b = service.create('user-b', 'Habit B')
    assert a['user_id'] != b['user_id']
    assert service.collection.find_one({'id': a['id']})['user_id'] == 'user-a'
    assert service.collection.find_one({'id': b['id']})['user_id'] == 'user-b'


# --- schema sanity ---

def test_valid_frequencies_constant_pin():
    """Catch silent expansion of allowed frequencies — schema changes should be deliberate."""
    assert VALID_FREQUENCIES == {'daily', 'weekly'}


# --- list ---

def test_get_all_empty(service):
    assert service.get_all('user-1') == []


def test_get_all_returns_user_habits(service):
    service.create('user-1', 'A')
    service.create('user-1', 'B')
    result = service.get_all('user-1')
    assert {h['name'] for h in result} == {'A', 'B'}


def test_get_all_isolates_users(service):
    service.create('user-a', 'Mine')
    service.create('user-b', 'Theirs')
    a_habits = service.get_all('user-a')
    assert len(a_habits) == 1
    assert a_habits[0]['name'] == 'Mine'


# --- get one ---

def test_get_one_returns_entry(service):
    created = service.create('user-1', 'Run')
    fetched = service.get_one('user-1', created['id'])
    assert fetched['id'] == created['id']
    assert fetched['name'] == 'Run'


def test_get_one_unknown_id_returns_none(service):
    assert service.get_one('user-1', 'nonexistent') is None


def test_get_one_foreign_user_returns_none(service):
    created = service.create('user-a', 'Private')
    assert service.get_one('user-b', created['id']) is None


# --- update ---

def test_update_name(service):
    created = service.create('user-1', 'Old')
    updated = service.update('user-1', created['id'], name='New')
    assert updated['name'] == 'New'
    assert updated['target_freq'] == 'daily'


def test_update_target_freq(service):
    created = service.create('user-1', 'Run', target_freq='daily')
    updated = service.update('user-1', created['id'], target_freq='weekly')
    assert updated['target_freq'] == 'weekly'
    assert updated['name'] == 'Run'


def test_update_partial_preserves_other_fields(service):
    created = service.create('user-1', 'Keep', target_freq='weekly')
    updated = service.update('user-1', created['id'], name='Changed')
    assert updated['name'] == 'Changed'
    assert updated['target_freq'] == 'weekly'


def test_update_empty_body_returns_unchanged(service):
    created = service.create('user-1', 'Same', target_freq='weekly')
    updated = service.update('user-1', created['id'])
    assert updated['name'] == 'Same'
    assert updated['target_freq'] == 'weekly'


def test_update_unknown_id_returns_none(service):
    assert service.update('user-1', 'nonexistent', name='X') is None


def test_update_foreign_user_returns_none(service):
    created = service.create('user-a', 'Private')
    assert service.update('user-b', created['id'], name='hijacked') is None
    # Original entry unchanged
    assert service.get_one('user-a', created['id'])['name'] == 'Private'


def test_update_invalid_name_raises(service):
    created = service.create('user-1', 'OK')
    with pytest.raises(ValueError, match='name'):
        service.update('user-1', created['id'], name='   ')


def test_update_invalid_target_freq_raises(service):
    created = service.create('user-1', 'OK')
    with pytest.raises(ValueError, match='target_freq'):
        service.update('user-1', created['id'], target_freq='hourly')


# --- delete ---

def test_delete_returns_true(service):
    created = service.create('user-1', 'Bye')
    assert service.delete('user-1', created['id']) is True


def test_delete_entry_is_gone(service):
    created = service.create('user-1', 'Gone')
    service.delete('user-1', created['id'])
    assert service.get_one('user-1', created['id']) is None


def test_delete_unknown_id_returns_false(service):
    assert service.delete('user-1', 'nonexistent') is False


def test_delete_foreign_user_returns_false(service):
    created = service.create('user-a', 'Protected')
    assert service.delete('user-b', created['id']) is False
    # Entry still there for the rightful owner
    assert service.get_one('user-a', created['id']) is not None
