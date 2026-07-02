"""Per-user ledger of every AI call (sentiment, transcription, ...).

Each call records model, token counts, duration, and USD cost. The ledger
also enforces a configurable daily budget:
    AI_DAILY_BUDGET_USD    hard cap  (0 or unset = unlimited)
    soft warning at 80% of the cap
"""
import os
from uuid import uuid4

from app.utils.tools import standard_now, utc_today
from app.db import get_db

SOFT_WARN_RATIO = 0.8

BUDGET_OK = 'ok'
BUDGET_WARN = 'warn'
BUDGET_BLOCK = 'block'


def daily_budget_usd() -> float:
    try:
        return max(float(os.getenv('AI_DAILY_BUDGET_USD', '0')), 0.0)
    except ValueError:
        return 0.0


class AILedger:
    def __init__(self, collection=None):
        if collection is None:
            self.collection = get_db()['ai_calls']
            self.collection.create_index('user_id')
            self.collection.create_index('called_at')
            self.collection.create_index('dedupe_key', unique=True, sparse=True)
        else:
            self.collection = collection

    def record(self, user_id: str, kind: str, model: str, cost_usd: float = 0.0,
               input_tokens: int = 0, output_tokens: int = 0,
               entry_id: str | None = None, duration_s: float | None = None,
               dedupe_key: str | None = None) -> dict:
        """Record one AI call. With dedupe_key set (e.g. the event id), a
        redelivered message records — and bills — only once."""
        call = {
            'id': str(uuid4()),
            'user_id': user_id,
            'entry_id': entry_id,
            'kind': kind,
            'model': model,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'duration_s': duration_s,
            'cost_usd': round(cost_usd, 6),
            'called_at': standard_now(),
        }
        if dedupe_key is None:
            self.collection.insert_one(call)
        else:
            self.collection.update_one(
                {'dedupe_key': dedupe_key},
                {'$setOnInsert': {**call, 'dedupe_key': dedupe_key}},
                upsert=True,
            )
        return {k: v for k, v in call.items() if k != '_id'}

    def _rollup(self, user_id: str, prefix: str) -> dict:
        calls = 0
        cost = 0.0
        by_kind: dict[str, int] = {}
        cursor = self.collection.find(
            {'user_id': user_id, 'called_at': {'$regex': f'^{prefix}'}}
        )
        for doc in cursor:
            calls += 1
            cost += doc.get('cost_usd') or 0.0
            by_kind[doc['kind']] = by_kind.get(doc['kind'], 0) + 1
        return {'calls': calls, 'cost_usd': round(cost, 6), 'by_kind': by_kind}

    def usage(self, user_id: str) -> dict:
        today = utc_today().isoformat()
        month = today[:7]
        budget = daily_budget_usd()
        report = {
            'today': self._rollup(user_id, today),
            'month': self._rollup(user_id, month),
            'daily_budget_usd': budget or None,
        }
        report['budget_status'] = self._status(report['today']['cost_usd'], budget)
        return report

    @staticmethod
    def _status(spent_today: float, budget: float) -> str:
        if not budget:
            return BUDGET_OK
        if spent_today >= budget:
            return BUDGET_BLOCK
        if spent_today >= budget * SOFT_WARN_RATIO:
            return BUDGET_WARN
        return BUDGET_OK

    def budget_status(self, user_id: str) -> str:
        budget = daily_budget_usd()
        if not budget:
            return BUDGET_OK
        spent = self._rollup(user_id, utc_today().isoformat())['cost_usd']
        return self._status(spent, budget)
