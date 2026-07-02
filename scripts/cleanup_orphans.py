"""Reconcile object storage with journal attachment metadata.

Two sweeps, both age-guarded so in-flight uploads are never touched:
- delete objects no longer referenced by any attachment;
- prune attachment metadata whose object was never uploaded (abandoned
  presign grants).

Run periodically (cron or manually):
    python scripts/cleanup_orphans.py
"""
import logging
import sys
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

from app.services.journal_service import JournalService
from app.services.storage_service import ORPHAN_MIN_AGE, StorageService
from app.utils.logging_config import configure_logging

logger = logging.getLogger('joy.cleanup')


def prune_dangling_metadata(journals: JournalService, storage: StorageService,
                            min_age: timedelta = ORPHAN_MIN_AGE) -> int:
    """Remove attachment metadata whose object never arrived. Returns count."""
    cutoff = datetime.now(timezone.utc) - min_age
    pruned = 0
    for user_id, entry_id, attachment in list(journals.all_attachments()):
        try:
            created = datetime.fromisoformat(attachment['created_at'])
        except (KeyError, ValueError):
            continue
        if created > cutoff:
            continue
        if storage.object_size(attachment['object_key']) is None:
            journals.remove_attachment(user_id, entry_id, attachment['id'])
            logger.info('pruned dangling attachment %s (entry %s)', attachment['id'], entry_id)
            pruned += 1
    return pruned


def main() -> int:
    load_dotenv()
    configure_logging()
    storage = StorageService()
    journals = JournalService()
    pruned = prune_dangling_metadata(journals, storage)
    referenced = journals.referenced_object_keys()
    deleted = storage.cleanup_orphans(referenced)
    logger.info('cleanup: %d dangling metadata pruned, %d referenced, %d orphans deleted',
                pruned, len(referenced), len(deleted))
    for key in deleted:
        logger.info('deleted orphan %s', key)
    return 0


if __name__ == '__main__':
    sys.exit(main())
