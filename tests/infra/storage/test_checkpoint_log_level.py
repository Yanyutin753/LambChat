"""Checkpointer acquisition logging must stay at debug level.

get_async_checkpointer runs on every graph invocation; logging "Using
MongoDB/PostgreSQL checkpointer" at INFO on each call floods the logs.
"""

from pathlib import Path

from src.infra.storage import checkpoint

SOURCE = Path(checkpoint.__file__).read_text(encoding="utf-8")


def test_backend_selection_logs_at_debug_not_info() -> None:
    assert 'logger.debug("Using PostgreSQL checkpointer")' in SOURCE
    assert 'logger.debug("Using MongoDB checkpointer")' in SOURCE
    assert 'logger.info("Using PostgreSQL checkpointer")' not in SOURCE
    assert 'logger.info("Using MongoDB checkpointer")' not in SOURCE
