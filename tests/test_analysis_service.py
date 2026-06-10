from unittest.mock import MagicMock
from app.services.analysis_service import AnalysisService, SENTIMENT_MODEL


def _stub(label: str, score: float):
    """Returns a callable mimicking the HuggingFace pipeline signature."""
    return MagicMock(return_value=[{'label': label, 'score': score}])


def test_analyze_normalizes_label_to_lowercase():
    svc = AnalysisService(pipeline=_stub('POSITIVE', 0.987))
    assert svc.analyze('I love it') == {'label': 'positive', 'score': 0.987}


def test_analyze_handles_negative_label():
    svc = AnalysisService(pipeline=_stub('NEGATIVE', 0.42))
    assert svc.analyze('I hate it') == {'label': 'negative', 'score': 0.42}


def test_analyze_calls_pipeline_with_text():
    pipe = _stub('POSITIVE', 0.9)
    svc = AnalysisService(pipeline=pipe)
    svc.analyze('Hello world')
    pipe.assert_called_once_with('Hello world')


def test_analyze_empty_string_returns_none():
    pipe = _stub('POSITIVE', 0.9)
    svc = AnalysisService(pipeline=pipe)
    assert svc.analyze('') is None
    pipe.assert_not_called()


def test_analyze_whitespace_only_returns_none():
    pipe = _stub('POSITIVE', 0.9)
    svc = AnalysisService(pipeline=pipe)
    assert svc.analyze('   \n  ') is None
    pipe.assert_not_called()


def test_analyze_score_is_float():
    svc = AnalysisService(pipeline=_stub('POSITIVE', 0.5))
    result = svc.analyze('text')
    assert isinstance(result['score'], float)


def test_default_model_name_constant():
    """Bootstrap script and service must reference the same model."""
    assert SENTIMENT_MODEL == 'distilbert-base-uncased-finetuned-sst-2-english'
    svc = AnalysisService(pipeline=_stub('POSITIVE', 0.9))
    assert svc._model_name == SENTIMENT_MODEL


def test_injected_pipeline_skips_lazy_load():
    """Service should never touch transformers when a pipeline is injected."""
    pipe = _stub('POSITIVE', 0.9)
    svc = AnalysisService(pipeline=pipe)
    svc.analyze('text')
    svc.analyze('again')
    assert pipe.call_count == 2
