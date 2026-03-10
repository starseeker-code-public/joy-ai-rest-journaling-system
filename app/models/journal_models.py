from dataclasses import dataclass, asdict
from uuid import uuid4
from app.utils.tools import standard_now

@dataclass
class JournalEntry:
    id: str
    title: str
    content: str
    date: str

    @classmethod
    def create(cls, title: str, content: str):
        return cls(
            id=str(uuid4()),
            title=title,
            content=content,
            date=standard_now()
        )
    
    def to_dict(self):
        return asdict(self)

