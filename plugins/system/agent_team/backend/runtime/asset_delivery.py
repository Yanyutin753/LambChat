"""Delivery evidence and path validation for Agent Team asset packages."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
_ARCHIVE_SUFFIXES = {".zip", ".tar", ".gz", ".tgz", ".7z"}
_DELIVERY_TOOL_NAMES = {
    "image_generate",
    "image_edit_with_references",
    "reveal_project",
    "reveal_file",
}


def uploaded_file_path_from_url(url: str, *, upload_root: str = "/app/uploads") -> str | None:
    """Map an internal upload URL to a file while containing it under ``upload_root``."""
    parsed = urlparse(url)
    marker = "/api/upload/file/"
    if marker not in parsed.path:
        return None

    key = unquote(parsed.path.split(marker, 1)[1]).replace("\\", "/")
    if not key or key.startswith("/"):
        return None

    root = Path(upload_root).resolve()
    candidate = (root / key).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return str(candidate)


def _coerce_payload(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return None
        return parsed if isinstance(parsed, dict) else None
    content = getattr(value, "content", None)
    if content is not None and content is not value:
        return _coerce_payload(content)
    return None


def reveal_project_files(value: Any) -> tuple[set[str], str | None]:
    """Return a verified reveal manifest or a concrete failure reason."""
    payload = _coerce_payload(value)
    if payload is None:
        return set(), "reveal_project returned a non-JSON result"
    if payload.get("error"):
        return set(), str(payload["error"])
    if payload.get("type") != "project_reveal":
        return set(), "reveal_project returned an unexpected result type"
    files = payload.get("files") or payload.get("files_manifest")
    if not isinstance(files, dict) or not files:
        return set(), "reveal_project returned no files"
    return {str(path) for path in files}, None


def _event_output(event: dict[str, Any]) -> Any:
    data = event.get("data")
    if not isinstance(data, dict):
        return None
    return data.get("output")


@dataclass
class AssetDeliveryEvidence:
    """Tool-backed evidence used to avoid duplicate or falsely successful delivery."""

    attempted_tools: set[str] = field(default_factory=set)
    revealed_files: set[str] = field(default_factory=set)
    reveal_errors: list[str] = field(default_factory=list)
    generated_image_count: int = 0

    def observe(self, event: Any) -> None:
        if not isinstance(event, dict):
            return
        event_type = str(event.get("event") or "")
        tool_name = str(event.get("name") or "").strip()
        if event_type not in {"on_tool_start", "on_tool_end", "on_tool_error"}:
            return
        if tool_name:
            self.attempted_tools.add(tool_name)
        if event_type == "on_tool_error" and tool_name == "reveal_project":
            self.reveal_errors.append("reveal_project raised an error")
            return
        if event_type != "on_tool_end":
            return
        if tool_name in {"image_generate", "image_edit_with_references"}:
            payload = _coerce_payload(_event_output(event))
            images = payload.get("images") if payload else None
            if payload and not payload.get("error") and isinstance(images, list):
                self.generated_image_count += len(images)
        if tool_name == "reveal_project":
            files, error = reveal_project_files(_event_output(event))
            if error:
                self.reveal_errors.append(error)
            else:
                self.revealed_files.update(files)

    @property
    def has_delivery_attempt(self) -> bool:
        return bool(self.attempted_tools & _DELIVERY_TOOL_NAMES)

    @property
    def image_files(self) -> set[str]:
        return {
            path for path in self.revealed_files if Path(path).suffix.casefold() in _IMAGE_SUFFIXES
        }

    @property
    def archive_files(self) -> set[str]:
        return {
            path
            for path in self.revealed_files
            if Path(path).suffix.casefold() in _ARCHIVE_SUFFIXES
        }

    @property
    def complete(self) -> bool:
        return bool(self.revealed_files and self.image_files and self.archive_files)

    def public_summary(self) -> str:
        status = "完整交付" if self.complete else "部分交付"
        lines = [
            f"完整素材包任务已{status}。",
            "",
            f"- 已验证交付文件：{len(self.revealed_files)} 个",
            f"- 已验证首帧图片：{len(self.image_files)} 个",
            f"- 已验证压缩包：{len(self.archive_files)} 个",
        ]
        if self.reveal_errors:
            lines.append(f"- reveal_project 失败：{self.reveal_errors[-1]}")
        if not self.complete:
            lines.append("- 未使用固定模板或占位图覆盖已有交付结果。")
        return "\n".join(lines)
