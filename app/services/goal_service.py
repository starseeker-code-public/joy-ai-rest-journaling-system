from uuid import uuid4
from pymongo import ReturnDocument
from app.utils.tools import standard_now, strip_doc
from app.utils.validators import parse_iso_date, require_string
from app.db import get_db

UNSET = object()  # distinguishes "field not provided" from an explicit null


def _validate_description(description):
    if description is None:
        return ''
    if not isinstance(description, str):
        raise ValueError('description must be a string')
    return description


def _validate_target_date(value):
    if value is None:
        return None
    return parse_iso_date(value, 'target_date').isoformat()


def _new_milestone(title) -> dict:
    return {
        'id': str(uuid4()),
        'title': require_string(title, 'title'),
        'completed': False,
        'completed_at': None,
    }


def _validate_milestones(milestones) -> list:
    if milestones is None:
        return []
    if not isinstance(milestones, list) or not all(isinstance(m, str) for m in milestones):
        raise ValueError('milestones must be a list of strings')
    return [_new_milestone(m) for m in milestones]


def _progress(milestones: list) -> float:
    """Fraction of completed milestones, 0.0 when there are none."""
    if not milestones:
        return 0.0
    done = sum(1 for m in milestones if m['completed'])
    return round(done / len(milestones), 4)


class GoalService:
    def __init__(self, collection=None):
        if collection is None:
            self.collection = get_db()['goals']
            self.collection.create_index('id', unique=True)
            self.collection.create_index('user_id')
        else:
            self.collection = collection

    def get_all(self, user_id: str) -> list:
        return [self._serialize(g) for g in self.collection.find({'user_id': user_id})]

    def get_one(self, user_id: str, uid: str) -> dict | None:
        goal = self.collection.find_one({'id': uid, 'user_id': user_id})
        return self._serialize(goal) if goal else None

    def create(self, user_id: str, title: str, description=None, target_date=None, milestones=None) -> dict:
        goal = {
            'id': str(uuid4()),
            'user_id': user_id,
            'title': require_string(title, 'title'),
            'description': _validate_description(description),
            'target_date': _validate_target_date(target_date),
            'milestones': _validate_milestones(milestones),
            'created_at': standard_now(),
        }
        self.collection.insert_one(goal)
        return self._serialize(goal)

    def update(self, user_id: str, uid: str, title=None, description=None, target_date=UNSET) -> dict | None:
        patch = {}
        if title is not None:
            patch['title'] = require_string(title, 'title')
        if description is not None:
            patch['description'] = _validate_description(description)
        if target_date is not UNSET:
            # An explicit null clears the target date
            patch['target_date'] = _validate_target_date(target_date)
        if not patch:
            return self.get_one(user_id, uid)
        goal = self.collection.find_one_and_update(
            {'id': uid, 'user_id': user_id},
            {'$set': patch},
            return_document=ReturnDocument.AFTER,
        )
        return self._serialize(goal) if goal else None

    def delete(self, user_id: str, uid: str) -> bool:
        return self.collection.delete_one({'id': uid, 'user_id': user_id}).deleted_count > 0

    def add_milestone(self, user_id: str, uid: str, title: str) -> dict | None:
        milestone = _new_milestone(title)
        goal = self.collection.find_one_and_update(
            {'id': uid, 'user_id': user_id},
            {'$push': {'milestones': milestone}},
            return_document=ReturnDocument.AFTER,
        )
        return self._serialize(goal) if goal else None

    def complete_milestone(self, user_id: str, uid: str, milestone_id: str) -> dict | None:
        """Mark a milestone complete. Idempotent (completed_at is set once).
        None if the goal or milestone is missing.

        Targets the milestone by array index rather than the positional `$`
        operator (mongomock mishandles `$` with $elemMatch and lacks
        arrayFilters). Milestones are append-only, so indexes are stable; the
        completed:False guard in the filter keeps repeat calls from rewriting
        completed_at.
        """
        goal = self.collection.find_one({'id': uid, 'user_id': user_id})
        if goal is None:
            return None
        index = next((i for i, m in enumerate(goal['milestones']) if m['id'] == milestone_id), None)
        if index is None:
            return None
        updated = self.collection.find_one_and_update(
            {
                'id': uid,
                'user_id': user_id,
                'milestones': {'$elemMatch': {'id': milestone_id, 'completed': False}},
            },
            {'$set': {
                f'milestones.{index}.completed': True,
                f'milestones.{index}.completed_at': standard_now(),
            }},
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:
            # Already complete: idempotent success with the current state
            updated = self.collection.find_one({'id': uid, 'user_id': user_id})
        return self._serialize(updated) if updated else None

    def _serialize(self, goal: dict) -> dict:
        goal = strip_doc(goal)
        goal['progress'] = _progress(goal['milestones'])
        return goal
