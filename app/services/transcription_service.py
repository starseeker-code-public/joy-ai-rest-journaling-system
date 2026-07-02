"""Whisper-based speech-to-text for voice journal entries.

The default transcriber lazily loads a local HuggingFace Whisper pipeline
(no external API). Tests inject a stub via the `transcriber` parameter.

Cost accounting: local inference is free by default, but the per-minute
rate is configurable (TRANSCRIPTION_USD_PER_MINUTE) so a hosted Whisper API
can be priced in; every transcription reports model, duration, and cost for
the v0.17 ledger.
"""
import os
import time

WHISPER_MODEL = os.getenv('WHISPER_MODEL', 'openai/whisper-tiny')
USD_PER_MINUTE = float(os.getenv('TRANSCRIPTION_USD_PER_MINUTE', '0'))


class TranscriptionService:
    def __init__(self, transcriber=None):
        self._transcriber = transcriber

    @property
    def transcriber(self):
        if self._transcriber is None:
            from transformers import pipeline
            self._transcriber = pipeline(
                'automatic-speech-recognition', model=WHISPER_MODEL
            )
        return self._transcriber

    def transcribe(self, audio_path: str) -> dict:
        """Returns {'text', 'model', 'duration_s', 'cost_usd'}."""
        started = time.perf_counter()
        result = self.transcriber(audio_path)
        duration_s = round(time.perf_counter() - started, 2)
        text = (result.get('text') or '').strip()
        return {
            'text': text,
            'model': WHISPER_MODEL,
            'duration_s': duration_s,
            'cost_usd': round(duration_s / 60 * USD_PER_MINUTE, 6),
        }
