"""
Localized recovery user messages for task resumption.

These messages are emitted as normal ``user:message`` events so the frontend
can keep rendering them without any protocol changes.
"""

from __future__ import annotations

from typing import Final

SUPPORTED_RECOVERY_LANGUAGES: Final[set[str]] = {"en", "zh", "ja", "ko", "ru"}

DEFAULT_RECOVERY_REASON = "server_restart"

_RECOVERY_MESSAGES: Final[dict[str, dict[str, str]]] = {
    "server_restart": {
        "en": "The previous task was interrupted due to a system restart. Please continue processing the unfinished content in the current session.",
        "zh": "由于系统重启，上一轮任务已中断。请继续处理当前会话中未完成的内容。",
        "ja": "システムの再起動により前回のタスクが中断されました。現在のセッションで未完了の内容の処理を継続してください。",
        "ko": "시스템 재시작으로 인해 이전 작업이 중단되었습니다. 현재 세션에서 완료되지 않은 내용을 계속 처리해 주세요.",
        "ru": "Предыдущая задача была прервана из-за перезапуска системы. Пожалуйста, продолжите обработку незавершенного содержимого в текущей сессии.",
    },
    "manual_resume": {
        "en": "Please continue processing the unfinished content in the current session.",
        "zh": "请继续处理当前会话中未完成的内容。",
        "ja": "現在のセッションで未完了の内容の処理を継続してください。",
        "ko": "현재 세션에서 완료되지 않은 내용을 계속 처리해 주세요.",
        "ru": "Пожалуйста, продолжите обработку незавершенного содержимого в текущей сессии.",
    },
}


def normalize_recovery_language(language: str | None) -> str:
    """Normalize a language code to one of the supported recovery locales."""
    if not language:
        return "en"
    normalized = language.split(",")[0].split("-")[0].strip().lower()
    return normalized if normalized in SUPPORTED_RECOVERY_LANGUAGES else "en"


def build_recovery_message(reason: str, language: str | None) -> str:
    """Build a localized recovery message for a resumed task."""
    localized_reason = _RECOVERY_MESSAGES.get(reason) or _RECOVERY_MESSAGES[DEFAULT_RECOVERY_REASON]
    normalized_language = normalize_recovery_language(language)
    return localized_reason.get(normalized_language) or localized_reason["en"]
