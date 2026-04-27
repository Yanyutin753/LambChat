"""Shared grep helpers for sandbox backends."""

from __future__ import annotations

import shlex

from deepagents.backends.protocol import ExecuteResponse, GrepMatch

_DEFAULT_GREP_TIMEOUT = 30
_EXCLUDED_GLOB_PATTERNS = (
    "!node_modules/**",
    "!.git/**",
    "!dist/**",
    "!build/**",
    "!.venv/**",
    "!venv/**",
    "!__pycache__/**",
)
_EXCLUDED_GREP_DIRECTORIES = (
    "node_modules",
    ".git",
    "dist",
    "build",
    ".venv",
    "venv",
    "__pycache__",
)
_EXCLUDED_GREP_FILES = ("*.tsbuildinfo",)


def get_sandbox_grep_timeout(settings_obj: object) -> int:
    """Return the configured grep timeout with a stable fallback."""
    value = getattr(settings_obj, "SANDBOX_GREP_TIMEOUT", _DEFAULT_GREP_TIMEOUT)
    try:
        timeout = int(value)
    except (TypeError, ValueError):
        return _DEFAULT_GREP_TIMEOUT
    return max(1, timeout)


def build_grep_command(pattern: str, path: str | None = None, glob: str | None = None) -> str:
    """Build a literal recursive grep command optimized for large code repositories."""
    search_path = shlex.quote(path or ".")
    pattern_escaped = shlex.quote(pattern)
    rg_globs = [glob, *_EXCLUDED_GLOB_PATTERNS] if glob else list(_EXCLUDED_GLOB_PATTERNS)
    rg_glob_clause = " ".join(f"--glob {shlex.quote(item)}" for item in rg_globs)
    grep_include_clause = f"--include={shlex.quote(glob)} " if glob else ""
    grep_exclude_dir_clause = " ".join(
        f"--exclude-dir={shlex.quote(directory)}" for directory in _EXCLUDED_GREP_DIRECTORIES
    )
    grep_exclude_file_clause = " ".join(
        f"--exclude={shlex.quote(file_name)}" for file_name in _EXCLUDED_GREP_FILES
    )
    rg_command = (
        "rg --fixed-strings --line-number --with-filename --no-heading --color never "
        f"{rg_glob_clause} {pattern_escaped} {search_path}"
    )
    grep_command = (
        f"grep -rHnF {grep_include_clause}{grep_exclude_dir_clause} {grep_exclude_file_clause} "
        f"-e {pattern_escaped} {search_path} 2>/dev/null"
    )
    return f"(command -v rg >/dev/null 2>&1 && {rg_command}) || {grep_command} || true"


def parse_grep_response(result: ExecuteResponse, timeout: int) -> list[GrepMatch] | str:
    """Parse grep output or surface a user-facing timeout error."""
    output = result.output.rstrip()
    if result.exit_code == -1 and "timed out" in output.lower():
        return f"Error: grep timed out after {timeout}s. Try a more specific pattern or a narrower path."

    if not output:
        return []

    matches: list[GrepMatch] = []
    for line in output.split("\n"):
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        try:
            line_number = int(parts[1])
        except ValueError:
            continue
        matches.append({"path": parts[0], "line": line_number, "text": parts[2]})

    return matches
