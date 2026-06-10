"""Sentiment analysis service wrapping a HuggingFace transformers pipeline.

The pipeline is loaded lazily on first call so importing this module does not
require the [ai] extra. Tests inject a stub callable to avoid pulling in
transformers / torch.
"""

SENTIMENT_MODEL = 'distilbert-base-uncased-finetuned-sst-2-english'


class AnalysisService:
    def __init__(self, pipeline=None, model_name: str = SENTIMENT_MODEL):
        self._pipeline = pipeline
        self._model_name = model_name

    def _get_pipeline(self):
        if self._pipeline is None:
            from transformers import pipeline as _pipeline
            self._pipeline = _pipeline('sentiment-analysis', model=self._model_name)
        return self._pipeline

    def analyze(self, text: str) -> dict | None:
        """Returns {'label': 'positive'|'negative', 'score': float} or None for empty input."""
        if not text or not text.strip():
            return None
        result = self._get_pipeline()(text)[0]
        return {
            'label': result['label'].lower(),
            'score': float(result['score']),
        }
