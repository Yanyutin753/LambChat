from __future__ import annotations

from pathlib import Path


def resolve_frontend_target(
    project_root: Path, frontend_dev_url: str
) -> tuple[str, Path | str] | None:
    static_dir = project_root / "static"
    if static_dir.exists():
        return ("static", static_dir)

    frontend_dist = project_root / "frontend" / "dist"
    if frontend_dist.exists():
        return ("static", frontend_dist)

    if frontend_dev_url.strip():
        return ("redirect", frontend_dev_url.rstrip("/"))

    return None
