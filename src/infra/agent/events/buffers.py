"""Small, bounded stream buffers used by agent event processing."""

import time

BufferKey = tuple[int, str | None, str | None]


class TextChunkBuffer:
    """Accumulate text chunks for one stream key and flush as joined text.

    The first chunk is flushed immediately so the user sees content right away;
    afterwards a flush triggers when either *flush_size* characters accumulate
    or *flush_interval* seconds elapse since the last flush, whichever comes
    first — a slowly-streaming small tail still surfaces on time instead of
    waiting for the size threshold. ``flush_interval <= 0`` disables the time
    dimension. ``_has_flushed`` persists across ``consume`` calls within the
    same run — call ``reset`` to start a fresh run.
    """

    __slots__ = (
        "_length",
        "_parts",
        "flush_size",
        "flush_interval",
        "key",
        "_has_flushed",
        "_last_flush_at",
    )

    def __init__(self, flush_size: int, flush_interval: float = 0.0) -> None:
        self.flush_size = flush_size
        self.flush_interval = flush_interval
        self._parts: list[str] = []
        self._length = 0
        self.key: BufferKey | None = None
        self._has_flushed = False
        self._last_flush_at = 0.0

    @property
    def has_pending(self) -> bool:
        return self._length > 0

    def key_changed(self, key: BufferKey) -> bool:
        return self.has_pending and self.key is not None and self.key != key

    def consume_ready(self, key: BufferKey) -> tuple[str, BufferKey | None] | None:
        """Consume pending text when appending a different stream key requires a flush."""
        if self.key_changed(key):
            return self.consume()
        return None

    def append(self, text: str, key: BufferKey) -> bool:
        """Append text and return whether a flush is requested.

        First chunk flushes immediately; afterwards the size or time threshold
        applies.
        """
        if not text:
            return False

        self._parts.append(text)
        self._length += len(text)
        self.key = key

        # First chunk → flush immediately so the user sees content without delay.
        if not self._has_flushed:
            self._has_flushed = True
            self._last_flush_at = time.monotonic()
            return True

        if self._length >= self.flush_size:
            self._last_flush_at = time.monotonic()
            return True

        if (
            self.flush_interval > 0
            and time.monotonic() - self._last_flush_at >= self.flush_interval
        ):
            self._last_flush_at = time.monotonic()
            return True

        return False

    def consume(self) -> tuple[str, BufferKey | None]:
        if not self.has_pending:
            key = self.key
            self.clear()
            return "", key

        text = "".join(self._parts)
        key = self.key
        self.clear()
        return text, key

    def clear(self) -> None:
        """Clear buffered content but keep the first-flush state."""
        self._parts.clear()
        self._length = 0
        self.key = None

    def reset(self) -> None:
        """Full reset for a new run — clears content and first-flush state."""
        self.clear()
        self._has_flushed = False
