"""Shared event-bus constants used by publisher, consumer, and producers."""

EXCHANGE_NAME = 'joy.events'
EXCHANGE_TYPE = 'topic'

# Routing keys
JOURNAL_CREATED = 'journal.created'
JOURNAL_UPDATED = 'journal.updated'
JOURNAL_DELETED = 'journal.deleted'
JOURNAL_ANALYZED = 'journal.analyzed'
