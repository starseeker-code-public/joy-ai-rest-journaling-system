"""Pre-download the sentiment model so the consumer doesn't pull it on first request.

Run once at image build time (or first container start) to cache weights locally.
Re-running is idempotent — HuggingFace skips the download if cached.

Usage:
    python scripts/bootstrap_model.py
"""

import logging
import sys

from app.services.analysis_service import SENTIMENT_MODEL

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
logger = logging.getLogger('joy.bootstrap')


def main() -> int:
    try:
        from transformers import pipeline
    except ImportError:
        logger.error('transformers is not installed. Install the [ai] extra: pip install -e ".[ai]"')
        return 1

    logger.info('Bootstrapping sentiment model: %s', SENTIMENT_MODEL)
    pipeline('sentiment-analysis', model=SENTIMENT_MODEL)
    logger.info('Model ready (cached locally).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
