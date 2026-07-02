"""Seed a demo account with sample data through the public API.

Usage (stack must be running):
    python scripts/seed_demo.py [--base-url http://localhost:8080]

Idempotent-ish: registration of an existing demo user is skipped and new
entries are appended.
"""
import argparse
import json
import sys
import urllib.request

DEMO_EMAIL = 'demo@joy.local'
DEMO_PASSWORD = 'demo-password-123'

ENTRIES = [
    {'title': 'Morning run', 'content': 'Felt amazing out in the sun, best run in weeks!',
     'mood': 9, 'tags': ['fitness', 'morning']},
    {'title': 'Deadline stress', 'content': 'Rough day, the release slipped again and everyone is tense.',
     'mood': 3, 'tags': ['work']},
    {'title': 'Dinner with friends', 'content': 'Great food and even better conversation. Grateful.',
     'mood': 8, 'tags': ['friends', 'gratitude']},
    {'title': 'Quiet Sunday', 'content': 'Read a book, drank tea, did absolutely nothing. Perfect.',
     'mood': 7, 'tags': ['rest']},
]

HABITS = [
    {'name': 'Meditate', 'frequency': 'daily'},
    {'name': 'Weekly review', 'frequency': 'weekly'},
]

GOALS = [
    {'title': 'Run a half-marathon', 'target_date': '2026-10-01',
     'milestones': ['5k without stopping', '10k race', '15k long run', 'race day']},
]


def call(base, path, payload=None, token=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f'{base}{path}', data=data,
                                 method=method or ('POST' if data else 'GET'))
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    try:
        with urllib.request.urlopen(req) as res:
            return json.loads(res.read() or 'null')
    except urllib.error.HTTPError as e:
        return {'error': e.read().decode(), 'status': e.code}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://localhost:8080')
    base = parser.parse_args().base_url.rstrip('/')

    call(base, '/auth/register', {'email': DEMO_EMAIL, 'password': DEMO_PASSWORD})
    login = call(base, '/auth/login', {'email': DEMO_EMAIL, 'password': DEMO_PASSWORD})
    token = login.get('token')
    if not token:
        print('login failed:', login, file=sys.stderr)
        return 1

    for entry in ENTRIES:
        created = call(base, '/api/journals', entry, token)
        print('entry:', created.get('title', created))
    for habit in HABITS:
        created = call(base, '/api/habits', habit, token)
        if 'id' in created:
            call(base, f"/api/habits/{created['id']}/check", {}, token)
        print('habit:', created.get('name', created))
    for goal in GOALS:
        created = call(base, '/api/goals', goal, token)
        if created.get('milestones'):
            first = created['milestones'][0]['id']
            call(base, f"/api/goals/{created['id']}/milestones/{first}/complete", {}, token)
        print('goal:', created.get('title', created))

    print(f'\nDemo account ready: {DEMO_EMAIL} / {DEMO_PASSWORD}')
    print(f'Open {base}/ and log in.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
