"""Classification helpers for the native memory backend."""

from __future__ import annotations

import re
import warnings
from typing import Any, Awaitable, Callable, Optional

with warnings.catch_warnings():
    warnings.simplefilter("ignore", SyntaxWarning)
    import jieba.posseg as pseg

from src.infra.memory.client.native.models import CJK_STOPWORDS, STOPWORDS, char_ngrams, has_cjk

_USEFUL_POS = frozenset({"n", "nr", "ns", "nt", "nz", "v", "vn", "a", "eng", "x"})

_CODE_MARKERS = (
    "import ",
    "def ",
    "class ",
    "traceback",
    "exception:",
    "error:",
    "git ",
    "pip install",
    "npm install",
    "npm run",
    "src/",
    "node_modules",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
)

_TRANSIENT_STARTS = (
    "正在",
    "现在",
    "刚刚",
    "我在看",
    "我在改",
    "我来",
    "让我",
    "准备",
    "先",
    "currently",
    "right now",
    "i am checking",
    "i'm checking",
    "i am looking",
    "i'm looking",
    "let me",
)

_TRANSIENT_CONTAINS = (
    "看一下",
    "改一下",
    "查一下",
    "reading",
    "checking",
    "searching",
)


def word_similarity(a: str, b: str) -> float:
    """Jaccard similarity — character n-grams for CJK, word sets otherwise."""
    if has_cjk(a) or has_cjk(b):
        set_a = char_ngrams(a, 2)
        set_b = char_ngrams(b, 2)
    else:
        set_a = set(a.lower().split())
        set_b = set(b.lower().split())
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def looks_like_code_or_path(content: str) -> bool:
    if content.count("/") + content.count("\\") >= 3:
        return True
    return any(marker in content for marker in _CODE_MARKERS)


def is_transient_status_content(content: str) -> bool:
    stripped = content.strip()
    return stripped.startswith(_TRANSIENT_STARTS) or any(
        marker in stripped.lower() for marker in _TRANSIENT_CONTAINS
    )


def passes_lightweight_memory_filter(content: str) -> bool:
    if len(content) < 5:
        return False
    if is_transient_status_content(content):
        return False
    if looks_like_code_or_path(content):
        return False
    return True


def is_manual_memory_worthy(content: str, context: Optional[str] = None) -> bool:
    stripped = content.strip()
    if len(stripped) < 5:
        return False
    # For explicit manual retention, skip transient/code filters entirely
    # — the user explicitly chose to save this content.
    if context and any(kw in context.lower() for kw in ("project", "reference")):
        return True
    if not passes_lightweight_memory_filter(stripped):
        return False
    return True


def extract_tags(content: str) -> list[str]:
    """Extract keyword tags using jieba for Chinese, whitespace for English."""
    tags: list[str] = []
    seen: set[str] = set()

    if has_cjk(content):
        cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", " ", content)
        words = pseg.cut(cleaned)
        for word, flag in words:
            w = word.strip()
            if not w or w in CJK_STOPWORDS or len(w) < 2:
                continue
            if flag not in _USEFUL_POS:
                continue
            if w not in seen:
                tags.append(w)
                seen.add(w)
    else:
        for w in content.lower().split():
            clean = w.strip(".,!?;:()[]{}\"'").lower()
            if len(clean) >= 3 and clean not in STOPWORDS and clean not in seen:
                tags.append(clean)
                seen.add(clean)

    return tags[:5]


async def deduplicate_against_existing(
    fetch_recent: Callable[[str], Awaitable[list[dict[str, Any]]]],
    user_id: str,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not candidates:
        return candidates

    recent = await fetch_recent(user_id)
    recent_summaries = [doc["summary"] for doc in recent if doc.get("summary")]
    if not recent_summaries:
        return candidates

    filtered = []
    for mem in candidates:
        summary = mem.get("summary", "")
        if not summary:
            filtered.append(mem)
            continue
        if any(
            word_similarity(summary, rs) > (0.55 if has_cjk(summary + rs) else 0.6)
            for rs in recent_summaries
        ):
            continue
        filtered.append(mem)
    return filtered


async def find_existing_memory_match(
    fetch_recent: Callable[[str], Awaitable[list[dict[str, Any]]]],
    user_id: str,
    summary: str,
    memory_type: str,
) -> dict[str, Any] | None:
    recent = await fetch_recent(user_id)
    best_match: dict[str, Any] | None = None
    best_score = 0.0
    threshold = 0.55 if has_cjk(summary) else 0.5

    for doc in recent:
        if doc.get("memory_type") != memory_type:
            continue
        existing_summary = str(doc.get("summary") or "").strip()
        if not existing_summary:
            continue
        score = word_similarity(summary, existing_summary)
        if score >= threshold and score > best_score:
            best_score = score
            best_match = doc
    return best_match
