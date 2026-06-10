from unittest.mock import MagicMock
from analysis_worker import make_handler


def _make_handler(analyze_return=None, analyze_side_effect=None):
    analysis = MagicMock()
    if analyze_side_effect is not None:
        analysis.analyze.side_effect = analyze_side_effect
    else:
        analysis.analyze.return_value = analyze_return
    journal = MagicMock()
    return make_handler(analysis, journal), analysis, journal


def test_handler_calls_analyze_with_content():
    handler, analysis, _ = _make_handler(analyze_return={'label': 'positive', 'score': 0.9})
    handler('journal.created', {'id': 'abc', 'user_id': 'u1', 'content': 'Great day'})
    analysis.analyze.assert_called_once_with('Great day')


def test_handler_uses_empty_string_when_content_missing():
    handler, analysis, _ = _make_handler(analyze_return=None)
    handler('journal.created', {'id': 'abc', 'user_id': 'u1'})
    analysis.analyze.assert_called_once_with('')


def test_handler_uses_empty_string_when_content_is_none():
    handler, analysis, _ = _make_handler(analyze_return=None)
    handler('journal.created', {'id': 'abc', 'user_id': 'u1', 'content': None})
    analysis.analyze.assert_called_once_with('')


def test_handler_short_circuits_on_none_analysis_result(caplog):
    handler, _, journal = _make_handler(analyze_return=None)
    with caplog.at_level('INFO', logger='joy.analysis'):
        handler('journal.created', {'id': 'xyz', 'user_id': 'u1', 'content': ''})
    assert any('sentiment=none' in r.getMessage() for r in caplog.records)
    journal.set_sentiment.assert_not_called()


def test_handler_logs_label_and_score(caplog):
    handler, _, _ = _make_handler(analyze_return={'label': 'positive', 'score': 0.876})
    with caplog.at_level('INFO', logger='joy.analysis'):
        handler('journal.created', {'id': 'xyz', 'user_id': 'u1', 'content': 'Good day'})
    msgs = [r.getMessage() for r in caplog.records]
    assert any('sentiment=positive' in m and 'score=0.876' in m and 'journal_id=xyz' in m for m in msgs)


def test_handler_persists_sentiment_to_journal_service():
    sentiment = {'label': 'positive', 'score': 0.95}
    handler, _, journal = _make_handler(analyze_return=sentiment)
    handler('journal.created', {'id': 'xyz', 'user_id': 'u1', 'content': 'Good day'})
    journal.set_sentiment.assert_called_once_with('u1', 'xyz', sentiment)


def test_handler_propagates_service_exceptions_to_consumer():
    """A failing analyze() should bubble — EventConsumer's nack path handles it."""
    handler, _, _ = _make_handler(analyze_side_effect=RuntimeError('model error'))
    try:
        handler('journal.created', {'id': 'abc', 'user_id': 'u1', 'content': 'text'})
    except RuntimeError:
        pass
    else:
        assert False, 'expected RuntimeError to propagate to EventConsumer'


# --- payload validation ---

def test_handler_skips_payload_missing_id():
    handler, analysis, journal = _make_handler(analyze_return={'label': 'positive', 'score': 0.9})
    handler('journal.created', {'user_id': 'u1', 'content': 'text'})
    analysis.analyze.assert_not_called()
    journal.set_sentiment.assert_not_called()


def test_handler_skips_payload_missing_user_id():
    handler, analysis, journal = _make_handler(analyze_return={'label': 'positive', 'score': 0.9})
    handler('journal.created', {'id': 'abc', 'content': 'text'})
    analysis.analyze.assert_not_called()
    journal.set_sentiment.assert_not_called()


def test_handler_skips_non_dict_payload():
    handler, analysis, _ = _make_handler(analyze_return={'label': 'positive', 'score': 0.9})
    handler('journal.created', ['not', 'a', 'dict'])
    analysis.analyze.assert_not_called()


def test_handler_truncates_oversize_content():
    from analysis_worker import MAX_CONTENT_CHARS
    handler, analysis, _ = _make_handler(analyze_return={'label': 'positive', 'score': 0.9})
    long_text = 'x' * (MAX_CONTENT_CHARS + 1000)
    handler('journal.created', {'id': 'abc', 'user_id': 'u1', 'content': long_text})
    passed = analysis.analyze.call_args.args[0]
    assert len(passed) == MAX_CONTENT_CHARS
