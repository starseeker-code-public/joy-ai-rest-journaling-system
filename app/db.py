import os

from pymongo import MongoClient

_client = None


def get_db():
    global _client
    if _client is None:
        _client = MongoClient(os.getenv('MONGO_URL', 'mongodb://localhost:27017'))
    return _client[os.getenv('MONGO_DB', 'joy')]
