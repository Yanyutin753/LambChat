"""Version comparison utilities."""

from typing import Optional

from packaging import version


def normalize_version(v: str) -> str:
    """Normalize version string, removing 'v' prefix."""
    if v and v.startswith("v"):
        return v[1:]
    return v


def has_new_version(current: str, latest: Optional[str]) -> bool:
    """Check if latest version is newer than current."""
    if not latest:
        return False
    try:
        current_norm = normalize_version(current)
        latest_norm = normalize_version(latest)
        return version.parse(latest_norm) > version.parse(current_norm)
    except Exception:
        # Fallback to string comparison if parsing fails
        return latest > current
