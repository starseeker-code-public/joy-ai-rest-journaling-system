"""Worker process: transcribes voice-note audio with Whisper.

Consumes journal.voice_uploaded, pulls the audio object from MinIO into a
temp file, runs the (local) Whisper pipeline, and persists the transcript
via JournalService.set_transcript — which publishes journal.transcribed so
the sentiment pipeline reruns over the transcribed text.
"""
import logging
import os
import tempfile
from dotenv import load_dotenv

from app.utils.event_consumer import EventConsumer
from app.utils.logging_config import configure_logging
from app.utils.tracing import configure_tracing, instrument_pika
from app.utils.events import JOURNAL_VOICE_UPLOADED
from app.utils.retry import with_retry
from app.services.journal_service import JournalService
from app.services.storage_service import StorageService
from app.services.transcription_service import TranscriptionService

logger = logging.getLogger('joy.transcription')


def make_handler(transcription_service, journal_service, storage_service, ledger=None):
    from app.services.ai_ledger import BUDGET_BLOCK, BUDGET_WARN

    def handle(routing_key: str, payload: dict) -> None:
        if not isinstance(payload, dict) or not all(
            payload.get(k) for k in ('id', 'user_id', 'attachment_id', 'object_key')
        ):
            logger.warning('skipping malformed payload for %s', routing_key)
            return
        event_id = payload.get('event_id')
        if ledger is not None:
            status = ledger.budget_status(payload['user_id'])
            if status == BUDGET_BLOCK:
                logger.warning('budget exceeded, skipping transcription user_id=%s',
                               payload['user_id'])
                # Zero-cost row: the skip stays discoverable in /api/me/usage,
                # and the user can re-POST /transcribe once the budget resets.
                ledger.record(payload['user_id'], 'transcription_blocked', '-',
                              entry_id=payload['id'],
                              dedupe_key=f'blocked:{event_id}' if event_id else None)
                return
            if status == BUDGET_WARN:
                logger.warning('budget nearly exhausted user_id=%s', payload['user_id'])
        suffix = os.path.splitext(payload['object_key'])[1] or '.audio'
        with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
            with_retry(
                lambda: storage_service.download_to(payload['object_key'], tmp.name),
                f'download {payload["object_key"]}',
            )
            result = transcription_service.transcribe(tmp.name)
        if ledger is not None:
            ledger.record(
                payload['user_id'], 'transcription', result['model'],
                cost_usd=result['cost_usd'], entry_id=payload['id'],
                duration_s=result['duration_s'],
                dedupe_key=f'transcription:{event_id}' if event_id else None,
            )
        # Retried: a transient Mongo blip must not discard a finished transcription
        updated = with_retry(
            lambda: journal_service.set_transcript(
                payload['user_id'], payload['id'], payload['attachment_id'], result,
            ),
            f'persist transcript journal_id={payload["id"]}',
        )
        if updated is None:
            logger.warning('entry or attachment vanished: journal_id=%s', payload['id'])
            return
        logger.info(
            'transcribed journal_id=%s attachment_id=%s chars=%d duration_s=%.2f',
            payload['id'], payload['attachment_id'], len(result['text']), result['duration_s'],
        )
    return handle


def main() -> None:
    load_dotenv()
    configure_logging()
    configure_tracing('joy-transcription-worker')
    instrument_pika()
    from app.utils.event_publisher import EventPublisher
    publisher = EventPublisher()
    journal_service = JournalService(publisher=publisher)
    from app.services.ai_ledger import AILedger
    handler = make_handler(TranscriptionService(), journal_service, StorageService(),
                           ledger=AILedger())
    consumer = EventConsumer(
        queue_name='journal-transcription',
        routing_keys=[JOURNAL_VOICE_UPLOADED],
    )
    logger.info('Transcription worker starting...')
    try:
        consumer.consume(handler)
    except KeyboardInterrupt:
        logger.info('Transcription worker stopping')
    finally:
        consumer.close()
        publisher.close()


if __name__ == '__main__':
    main()
