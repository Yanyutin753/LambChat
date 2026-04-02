"""Shared models and constants for the native memory backend."""

from __future__ import annotations

import re
from datetime import datetime, timezone

COLLECTION_NAME = "native_memories"

STOPWORDS = frozenset(
    "the a an is are was were be been being have has had do does did will would "
    "could should may might can shall to of in for on with at by from as into "
    "through and but or not this that it its i my me you your we our they their "
    "he she his her also just very so if then when where what how which who "
    "there here about up out all some any no each every both few more most "
    "other some such only own same than too most".split()
)

CJK_STOPWORDS = frozenset(
    "的 了 是 在 和 与 也 都 就 要 会 能 有 这 那 一 不 个 吧 啊 呢 吗 呀 "
    "把 被 让 给 对 从 到 向 比 用 以 为 所 之 其 着 过 地 得 很 已 还 "
    "再 又 却 并 因为 所以 如果 但是 而且 或者 虽然 不过".split()
)


def ensure_aware(dt: datetime) -> datetime:
    """Make a datetime timezone-aware (UTC) if it is naive."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def has_cjk(text: str) -> bool:
    """Check if text contains CJK characters."""
    return any("\u4e00" <= c <= "\u9fff" for c in text)


def char_ngrams(text: str, n: int = 2) -> set[str]:
    """Extract character n-grams from text, useful for Chinese similarity."""
    cleaned = re.sub(r"\s+", "", text)
    if len(cleaned) < n:
        return set()
    return {cleaned[i : i + n] for i in range(len(cleaned) - n + 1)}


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
