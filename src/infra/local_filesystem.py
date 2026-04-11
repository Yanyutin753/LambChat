"""Helpers for local filesystem preparation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.infra.logging import get_logger

logger = get_logger(__name__)


def ensure_local_filesystem_dirs(
    settings: Any,
    *,
    default_upload_dir: str | Path = "./uploads",
) -> None:
    """Create local directories that the app expects to exist at startup."""
    upload_path = Path(getattr(settings, "LOCAL_STORAGE_PATH", "") or default_upload_dir)

    required_paths: list[Path] = [
        upload_path,
        upload_path / "revealed_files",
        upload_path / "revealed_projects",
    ]

    for path in required_paths:
        path.mkdir(parents=True, exist_ok=True)
        logger.info("Ensured local directory exists: %s", path.resolve())
