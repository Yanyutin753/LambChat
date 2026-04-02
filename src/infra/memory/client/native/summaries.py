"""Summary and label helpers for the native memory backend."""

from __future__ import annotations

from src.infra.memory.client.native.models import has_cjk


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


async def llm_build_summary(backend, content: str) -> str:
    """Use LLM to generate a concise summary. Falls back to build_summary."""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        model = backend._get_memory_model()
        response = await model.ainvoke(
            [
                SystemMessage(
                    content="Summarize in at most 80 characters. Output ONLY the summary, nothing else."
                ),
                HumanMessage(
                    content=f"Summarize this memory in at most 80 characters (Chinese or English):\n\n{content[:500]}"
                ),
            ],
        )
        text = response.content
        if isinstance(text, list):
            for item in text:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    break
            else:
                return build_summary(content)
        summary = str(text).strip().strip("\"'")
        if summary and len(summary) <= 120:
            return summary[:100]
    except Exception as e:
        backend_logger = getattr(backend, "_logger", None)
        if backend_logger:
            backend_logger.debug("[NativeMemory] LLM summary failed, using rule-based: %s", e)
    return build_summary(content)


async def llm_build_title(backend, content: str) -> str:
    """Use LLM to generate a short title. Falls back to summary truncation."""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        model = backend._get_memory_model()
        response = await model.ainvoke(
            [
                SystemMessage(
                    content="Generate a short title in at most 25 characters. Output ONLY the title."
                ),
                HumanMessage(
                    content=f"Give this memory a concise title (max 25 chars, Chinese or English):\n\n{content[:300]}"
                ),
            ],
        )
        text = response.content
        if isinstance(text, list):
            for item in text:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    break
            else:
                return build_summary(content, 25)
        title = str(text).strip().strip("\"'")
        if title and len(title) <= 40:
            return title[:25]
    except Exception as e:
        backend_logger = getattr(backend, "_logger", None)
        if backend_logger:
            backend_logger.debug("[NativeMemory] LLM title failed, using fallback: %s", e)
    return build_summary(content, 25)


def build_index_label(title: str, summary: str, content: str) -> str:
    """Build a compact deterministic label for memory indexes without extra LLM calls."""
    seed = (title or summary or content).strip()
    if not seed:
        return ""
    return build_summary(seed, 12)
