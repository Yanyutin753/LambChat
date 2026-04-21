"""Small, bounded stream buffers used by agent event processing."""

BufferKey = tuple[int, str | None, str | None]


class TextChunkBuffer:
    """Accumulate text chunks for one stream key and flush as joined text."""

    __slots__ = ("_length", "_parts", "flush_size", "key")

    def __init__(self, flush_size: int) -> None:
        self.flush_size = flush_size
        self._parts: list[str] = []
        self._length = 0
        self.key: BufferKey | None = None

    @property
    def has_pending(self) -> bool:
        return self._length > 0

    def key_changed(self, key: BufferKey) -> bool:
        return self.has_pending and self.key is not None and self.key != key

    def append(self, text: str, key: BufferKey) -> bool:
        """Append text and return whether size threshold asks for a flush."""
        if not text:
            return False

        self._parts.append(text)
        self._length += len(text)
        self.key = key
        return self._length >= self.flush_size

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
        self._parts.clear()
        self._length = 0
        self.key = None
