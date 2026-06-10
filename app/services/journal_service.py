from uuid import uuid4
from app.utils.tools import get_storage, load_json, save_json, standard_now

class JournalService:
    def __init__(self, path: str = 'data/journals.json'):
        self.path = get_storage(path)

    def get_all(self) -> list:
        return load_json(self.path)

    def get_one(self, uid: str) -> dict | None:
        return next((e for e in self.get_all() if e['id'] == uid), None)

    def create(self, title: str, content: str) -> dict:
        entries = self.get_all()
        entry = {
            'id': str(uuid4()),
            'title': title,
            'content': content,
            'date': standard_now()
        }
        entries.append(entry)
        save_json(self.path, entries)
        return entry

    def update(self, uid: str, title: str | None = None, content: str | None = None) -> dict | None:
        entries = self.get_all()
        for e in entries:
            if e['id'] == uid:
                if title: e['title'] = title
                if content: e['content'] = content
                e['date'] = standard_now()
                save_json(self.path, entries)
                return e
        return None

    def delete(self, uid: str) -> bool:
        entries = self.get_all()
        new = [e for e in entries if e['id'] != uid]
        if len(new) < len(entries):
            save_json(self.path, new)
            return True
        return False

