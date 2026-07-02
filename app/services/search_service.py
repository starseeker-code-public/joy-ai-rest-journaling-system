"""Full-text journal search backed by OpenSearch.

The API queries the index; the search_indexer worker keeps it in sync by
consuming journal.created / journal.updated / journal.deleted events.
"""
import os

INDEX_NAME = 'journals'

INDEX_BODY = {
    'mappings': {
        'properties': {
            'id': {'type': 'keyword'},
            'user_id': {'type': 'keyword'},
            'title': {'type': 'text'},
            'content': {'type': 'text'},
            'tags': {'type': 'keyword'},
            'kind': {'type': 'keyword'},
            'mood': {'type': 'integer'},
            'date': {'type': 'date'},
        }
    }
}

# Only these fields are indexed; ai results and anything else stay out
INDEXED_FIELDS = ('id', 'user_id', 'title', 'content', 'tags', 'kind', 'mood', 'date')

MAX_LIMIT = 100


def _default_client():
    from opensearchpy import OpenSearch
    return OpenSearch(os.getenv('OPENSEARCH_URL', 'http://localhost:9200'))


class SearchService:
    def __init__(self, client=None):
        self.client = client if client is not None else _default_client()

    def ensure_index(self) -> None:
        if not self.client.indices.exists(index=INDEX_NAME):
            self.client.indices.create(index=INDEX_NAME, body=INDEX_BODY)

    def index_entry(self, entry: dict) -> None:
        doc = {field: entry.get(field) for field in INDEXED_FIELDS}
        self.client.index(index=INDEX_NAME, id=doc['id'], body=doc)

    def delete_entry(self, entry_id: str) -> None:
        self.client.delete(index=INDEX_NAME, id=entry_id, params={'ignore': 404})

    def search(
        self,
        user_id: str,
        q: str | None = None,
        tags: list[str] | None = None,
        kind: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        filters = [{'term': {'user_id': user_id}}]
        if tags:
            filters.append({'terms': {'tags': tags}})
        if kind:
            filters.append({'term': {'kind': kind}})
        if date_from or date_to:
            date_range = {}
            if date_from:
                date_range['gte'] = date_from
            if date_to:
                if len(date_to) == 10:  # bare YYYY-MM-DD: include the whole day
                    date_range['lt'] = f'{date_to}||+1d/d'
                else:
                    date_range['lte'] = date_to
            filters.append({'range': {'date': date_range}})

        query: dict = {'bool': {'filter': filters}}
        if q:
            query['bool']['must'] = [
                {'multi_match': {'query': q, 'fields': ['title^2', 'content']}}
            ]

        body = {
            'query': query,
            'size': min(max(limit, 1), MAX_LIMIT),
            'sort': ['_score'] if q else [{'date': {'order': 'desc'}}],
        }
        response = self.client.search(index=INDEX_NAME, body=body)
        return [hit['_source'] for hit in response['hits']['hits']]
