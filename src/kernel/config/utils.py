"""Configuration utility functions."""

from __future__ import annotations

import base64
import hashlib
import logging
import subprocess
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Project root directory (where pyproject.toml is)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


def expand_jwt_secret_key(key: str, min_length: int = 32) -> str:
    """Expand a short JWT secret key to the minimum required length.

    Uses deterministic SHA-256 hashing to expand short keys to 32 bytes.
    This ensures the same input always produces the same output.

    Args:
        key: The original secret key (can be any length)
        min_length: Minimum required length

    Returns:
        A 32-byte URL-safe base64-encoded key
    """
    if len(key) >= min_length:
        return key

    # Use SHA-256 to deterministically expand the key
    # Repeatedly hash until we get 32 bytes
    result = key.encode("utf-8")
    while len(result) < 32:
        result = hashlib.sha256(result).digest()

    # Encode to URL-safe base64 (produces ~43-44 characters)
    return base64.urlsafe_b64encode(result).decode("utf-8").rstrip("=")


def get_app_version() -> str:
    """Read version from pyproject.toml."""
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    try:
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
            return data.get("project", {}).get("version", "1.0.0")
    except Exception as e:
        logger.warning(f"Failed to read version from pyproject.toml: {e}")
        return "1.0.0"


def get_default_from_settings(key: str, definitions: dict | None = None) -> Any:
    """Get default value from SETTING_DEFINITIONS"""
    if definitions is None:
        from src.kernel.config.definitions import SETTING_DEFINITIONS

        definitions = SETTING_DEFINITIONS
    if key in definitions:
        return definitions[key].get("default")
    return None


def get_git_info() -> tuple[str | None, str | None]:
    """Get git tag and commit hash at startup.

    Returns:
        tuple of (git_tag, commit_hash) or (None, None) if not in a git repo
    """
    try:
        # Get git describe (tag or commit)
        result = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        describe = result.stdout.strip() if result.returncode == 0 else None

        # Get commit hash
        hash_result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        commit_hash = hash_result.stdout.strip() if hash_result.returncode == 0 else None

        # If describe looks like a tag (starts with v), use it as tag
        git_tag = describe if describe and describe.startswith("v") else None

        return git_tag, commit_hash
    except Exception:
        return None, None


# Get git info at module load time
GIT_TAG, COMMIT_HASH = get_git_info()
