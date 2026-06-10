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
