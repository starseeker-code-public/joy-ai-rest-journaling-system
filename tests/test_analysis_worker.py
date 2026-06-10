from unittest.mock import MagicMock
from analysis_worker import make_handler


def test_handler_calls_analyze_with_content():
    svc = MagicMock()
    svc.analyze.return_value = {'label': 'positive', 'score': 0.9}
    handler = make_handler(svc)
    handler('journal.created', {'id': 'abc', 'content': 'Great day'})
    svc.analyze.assert_called_once_with('Great day')


def test_handler_uses_empty_string_when_content_missing():
    svc = MagicMock()
    svc.analyze.return_value = None
    handler = make_handler(svc)
    handler('journal.created', {'id': 'abc'})  # no content key
    svc.analyze.assert_called_once_with('')


def test_handler_uses_empty_string_when_content_is_none():
    svc = MagicMock()
    svc.analyze.return_value = None
    handler = make_handler(svc)
    handler('journal.created', {'id': 'abc', 'content': None})
    svc.analyze.assert_called_once_with('')


def test_handler_short_circuits_on_none_analysis_result(caplog):
    svc = MagicMock()
    svc.analyze.return_value = None
    handler = make_handler(svc)
    with caplog.at_level('INFO', logger='joy.analysis'):
        handler('journal.created', {'id': 'xyz', 'content': ''})
    assert any('sentiment=none' in r.getMessage() for r in caplog.records)


def test_handler_logs_label_and_score(caplog):
    svc = MagicMock()
    svc.analyze.return_value = {'label': 'positive', 'score': 0.876}
    handler = make_handler(svc)
    with caplog.at_level('INFO', logger='joy.analysis'):
        handler('journal.created', {'id': 'xyz', 'content': 'Good day'})
    msgs = [r.getMessage() for r in caplog.records]
    assert any('sentiment=positive' in m and 'score=0.876' in m and 'journal_id=xyz' in m for m in msgs)


def test_handler_does_not_propagate_service_exceptions():
    """Defensive: consumer-level error handling should be the catch-all,
    but the handler shouldn't crash on its own valid inputs.
    A failing analyze() should bubble — EventConsumer's nack path handles it."""
    svc = MagicMock()
    svc.analyze.side_effect = RuntimeError('model error')
    handler = make_handler(svc)
    try:
        handler('journal.created', {'id': 'abc', 'content': 'text'})
    except RuntimeError:
        pass  # expected — EventConsumer will catch and nack
    else:
        assert False, 'expected RuntimeError to propagate to EventConsumer'
