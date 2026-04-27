"""Helpers for local filesystem preparation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.infra.logging import get_logger

logger = get_logger(__name__)


def should_prepare_local_filesystem(settings: Any) -> bool:
    """Whether this process should rely on local filesystem storage paths."""
    if not getattr(settings, "S3_ENABLED", False):
        return True
    return str(getattr(settings, "S3_PROVIDER", "") or "").lower() == "local"


def ensure_local_filesystem_dirs(
    settings: Any,
    *,
    default_upload_dir: str | Path = "./uploads",
) -> None:
    """Create local directories that the app expects to exist at startup."""
    if not should_prepare_local_filesystem(settings):
        logger.info("Skipping local filesystem directory preparation for object storage mode")
        return

    upload_path = Path(getattr(settings, "LOCAL_STORAGE_PATH", "") or default_upload_dir)

    required_paths: list[Path] = [
        upload_path,
        upload_path / "revealed_files",
        upload_path / "revealed_projects",
    ]

    for path in required_paths:
        path.mkdir(parents=True, exist_ok=True)
        logger.info("Ensured local directory exists: %s", path.resolve())
