import json
from pathlib import Path
from datetime import datetime, timezone

def standard_now():
    return datetime.now(timezone.utc).isoformat()

def get_storage(path_str):
    path = Path(path_str)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([]))
    return path

def load_json(path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return []

def save_json(path, data):
    path.write_text(json.dumps(data, indent=4))

