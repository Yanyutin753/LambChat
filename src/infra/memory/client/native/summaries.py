"""Summary and label helpers for the native memory backend."""

from __future__ import annotations

import json
import logging
import warnings
from typing import Any

with warnings.catch_warnings():
    warnings.simplefilter("ignore", SyntaxWarning)
    import jieba.posseg as pseg

from src.infra.memory.client.native.models import CJK_STOPWORDS, has_cjk

logger = logging.getLogger(__name__)


def build_summary(content: str, max_len: int = 100) -> str:
    """Take the first sentence from content, supporting both CJK and English."""
    flat = content.replace("\n", " ").strip()

    best_pos = len(flat)
    for marker in ("。", "！", "？", ". ", "! ", "? ", "；", "; "):
        pos = flat.find(marker)
        if pos != -1 and pos < best_pos:
            best_pos = pos + len(marker)

    first_sentence = flat[:best_pos].strip()
    if first_sentence and len(first_sentence) <= max_len:
        return first_sentence

    if len(flat) <= max_len:
        return flat
    if has_cjk(flat):
        return flat[:max_len].strip() + "..."
    truncated = flat[:max_len]
    last_space = truncated.rfind(" ")
    if last_space > max_len // 2:
        return truncated[:last_space].strip() + "..."
    return truncated.strip() + "..."


def build_index_label(title: str, summary: str, content: str) -> str:
    """Build a compact deterministic label for memory indexes without extra LLM calls."""
    seed = (title or summary or content).strip()
    if not seed:
        return ""
    return build_summary(seed, 12)


def _fallback_tags(content: str) -> list[str]:
    """Rule-based tag fallback when LLM is unavailable."""
    from src.infra.memory.client.native.classification import extract_tags

    return extract_tags(content)


_ENRICH_SYSTEM = (
    "You are a memory tagging assistant. Respond with ONLY a JSON object, no markdown or explanation.\n"
    'Keys: "title" (max 25 chars), "summary" (max 80 chars), "tags" (array of 3-5 keyword strings).\n'
    "Tags should be meaningful keywords, NOT sliding character windows. Use the language of the input."
)


async def llm_enrich_memory(backend: Any, content: str) -> dict[str, Any]:
    """Single LLM call to extract title, summary, and tags together."""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        model = await backend._get_memory_model()
        response = await model.ainvoke(
            [
                SystemMessage(content=_ENRICH_SYSTEM),
                HumanMessage(content=f"Annotate this memory:\n\n{content[:500]}"),
            ],
        )
        text = response.content
        if isinstance(text, list):
            for item in text:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    break
            else:
                return _fallback_enrich(content)

        text = str(text).strip().strip("```json").strip("```").strip()
        data = json.loads(text)
        return {
            "title": str(data.get("title", ""))[:25] or build_summary(content, 25),
            "summary": str(data.get("summary", ""))[:100] or build_summary(content),
            "tags": [
                str(t) for t in (data.get("tags") or []) if isinstance(t, str) and len(t) >= 2
            ][:5]
            or _fallback_tags(content),
        }
    except Exception as e:
        logger.debug("[NativeMemory] LLM enrich failed, using fallback: %s", e)
        return _fallback_enrich(content)


def _fallback_title(content: str, summary: str) -> str:
    """Build a short title that differs from the summary — extract key nouns/phrases."""
    import re

    flat = content.replace("\n", " ").strip()
    if has_cjk(flat):
        clause = flat
        for sep in ("，", "。", "！", "？", "；", "、"):
            pos = flat.find(sep)
            if 2 < pos < len(clause):
                clause = flat[:pos]
        try:
            words = [
                (w, f)
                for w, f in pseg.cut(clause)
                if w.strip() and len(w) >= 2 and f in ("n", "nr", "ns", "nt", "nz", "eng", "vn")
            ][:3]
            if words:
                title = "".join(w for w, _ in words)
                return title[:25] if len(title) > 25 else title
        except Exception:
            pass
        return build_summary(flat, 25)

    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", flat)
    stop: set[str] = set(CJK_STOPWORDS) | {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "and",
        "but",
        "or",
        "not",
        "this",
        "that",
        "it",
        "its",
        "i",
        "my",
        "me",
        "you",
        "your",
        "we",
        "our",
        "they",
        "their",
        "he",
        "she",
    }
    keyword_words: list[str] = [w for w in cleaned.split() if w.lower() not in stop and len(w) >= 3]
    title = " ".join(keyword_words[:4]) if keyword_words else ""
    if not title or len(title) < 3:
        return build_summary(flat, 25)
    if len(title) > 25:
        result = ""
        for w in keyword_words:
            candidate = f"{result} {w}".strip()
            if len(candidate) > 25:
                break
            result = candidate
        title = result or build_summary(flat, 25)
    if title == summary[: len(title)]:
        title = build_summary(flat, 25)
    return title


def _fallback_enrich(content: str) -> dict[str, Any]:
    """Rule-based fallback for all enrich fields."""
    summary = build_summary(content)
    title = _fallback_title(content, summary)
    return {
        "title": title,
        "summary": summary,
        "tags": _fallback_tags(content),
    }
