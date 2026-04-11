"""Classification helpers for the native memory backend."""

from __future__ import annotations

import re
from typing import Any, Awaitable, Callable, Optional

from src.infra.memory.client.native.models import CJK_STOPWORDS, STOPWORDS, char_ngrams, has_cjk
from src.infra.memory.client.types import HIGH_SIGNAL_PATTERNS, MemoryType


def classify_type(content: str, context: Optional[str] = None) -> str:
    """Rule-based memory type classification."""
    content_lower = content.lower()

    if context:
        ctx_lower = context.lower()
        for mt in MemoryType:
            if mt.value in ctx_lower:
                return mt.value

    scores: dict[str, float] = {}
    for mtype, patterns in HIGH_SIGNAL_PATTERNS.items():
        score = 0
        for pat in patterns:
            if re.search(pat, content_lower):
                score += 1
        if score > 0:
            scores[mtype] = score

    if scores:
        max_score = max(scores.values())
        for mt in [
            MemoryType.FEEDBACK,
            MemoryType.REFERENCE,
            MemoryType.PROJECT,
            MemoryType.USER,
        ]:
            if mt.value in scores and scores[mt.value] == max_score:
                return mt.value

    return MemoryType.USER


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
    lowered = content.lower()
    if content.count("/") + content.count("\\") >= 3:
        return True
    code_markers = (
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
    return any(marker in lowered for marker in code_markers)


def is_transient_status_content(content: str) -> bool:
    stripped = content.strip()
    starts = (
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
    markers = (
        "看一下",
        "改一下",
        "查一下",
        "reading",
        "checking",
        "searching",
        "definitions.py",
        "nodes.py",
        "base.py",
    )
    lowered = stripped.lower()
    return stripped.startswith(starts) or any(marker in lowered for marker in markers)


def passes_lightweight_memory_filter(content: str) -> bool:
    stripped = content.strip()
    if len(stripped) < 20:
        return False
    if is_transient_status_content(stripped):
        return False
    if looks_like_code_or_path(stripped):
        return False
    return True


def is_manual_memory_worthy(content: str, context: Optional[str] = None) -> bool:
    stripped = content.strip()
    if len(stripped) < 10:
        return False
    if not passes_lightweight_memory_filter(stripped):
        return False
    if context:
        ctx = context.lower()
        if "project" in ctx or "reference" in ctx:
            return True
    return True


def extract_tags(content: str) -> list[str]:
    """Extract keyword tags. Supports both English and Chinese."""
    tags: list[str] = []
    seen: set[str] = set()

    if has_cjk(content):
        chunks = []
        current: list[str] = []
        for c in content:
            if c in "，。！？、；：''【】（）《》\t\n\r ":
                if current:
                    chunks.append("".join(current))
                    current = []
            else:
                current.append(c)
        if current:
            chunks.append("".join(current))

        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk or chunk in CJK_STOPWORDS:
                continue
            if 2 <= len(chunk) <= 4:
                if chunk not in seen:
                    tags.append(chunk)
                    seen.add(chunk)
            elif len(chunk) > 4:
                for i in range(len(chunk) - 2):
                    seg = chunk[i : i + 3]
                    if any(sw in seg for sw in ("的", "了", "是", "在")):
                        continue
                    if seg not in seen:
                        tags.append(seg)
                        seen.add(seg)
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
            word_similarity(summary, rs) > (0.55 if has_cjk(summary + rs) else 0.7)
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
