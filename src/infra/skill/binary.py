"""
Skill binary file utilities

Handles detection, storage reference building, and parsing of binary files in skills.
Binary files are stored in S3/local storage, with a JSON reference in MongoDB.
"""

import json
import mimetypes
from typing import Optional

from pydantic import BaseModel, Field

# Known binary file extensions (files that should go to S3, not MongoDB text storage)
BINARY_EXTENSIONS: set[str] = {
    # Images
    "jpg",
    "jpeg",
    "png",
    "gif",
    "webp",
    "bmp",
    "ico",
    "tiff",
    "tif",
    # Video
    "mp4",
    "webm",
    "mov",
    "avi",
    "mkv",
    "wmv",
    "flv",
    # Audio
    "mp3",
    "wav",
    "ogg",
    "aac",
    "flac",
    "m4a",
    "wma",
    # Binary documents
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    # Archives
    "zip",
    "tar",
    "gz",
    "bz2",
    "7z",
    "rar",
    # Fonts
    "woff",
    "woff2",
    "ttf",
    "eot",
    "otf",
    # Other binary
    "exe",
    "dll",
    "so",
    "dylib",
    "bin",
    "dat",
}

# Marker to identify binary references in MongoDB content field
BINARY_REF_MARKER = '"_binary_ref": true'


class SkillBinaryRef(BaseModel):
    """Binary file reference stored in MongoDB content field"""

    model_config = {"populate_by_name": True}

    binary_ref: bool = Field(default=True, alias="_binary_ref")
    storage_key: str  # S3/local storage key
    mime_type: str
    size: int


def is_binary_file(file_path: str, data: Optional[bytes] = None) -> bool:
    """
    Determine if a file should be treated as binary.

    Strategy:
    1. Check known binary extensions → binary
    2. If data provided, try UTF-8 decode → binary if fails
    3. Default to text
    """
    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""

    # Known binary extensions
    if ext in BINARY_EXTENSIONS:
        return True

    # Known text extensions — definitely not binary
    text_exts = {
        "md",
        "txt",
        "py",
        "js",
        "ts",
        "tsx",
        "jsx",
        "json",
        "yaml",
        "yml",
        "toml",
        "xml",
        "csv",
        "html",
        "htm",
        "css",
        "scss",
        "less",
        "sh",
        "bat",
        "ps1",
        "sql",
        "rb",
        "go",
        "rs",
        "java",
        "c",
        "cpp",
        "h",
        "hpp",
        "cs",
        "php",
        "swift",
        "kt",
        "scala",
        "r",
        "lua",
        "pl",
        "ex",
        "exs",
        "erl",
        "clj",
        "hs",
        "ml",
        "vim",
        "el",
        "lisp",
        "cfg",
        "ini",
        "conf",
        "env",
        "gitignore",
        "dockerignore",
        "dockerfile",
        "makefile",
        "cmake",
        "gradle",
    }
    if ext in text_exts:
        return False

    # Unknown extension — try to decode if data available
    if data is not None:
        # Quick check: null bytes almost always indicate binary
        if b"\x00" in data[:8192]:
            return True
        try:
            data.decode("utf-8")
            return False
        except (UnicodeDecodeError, ValueError):
            return True

    # Default: treat unknown extensions without data as text
    return False


def build_storage_key(user_id: str, skill_name: str, file_path: str) -> str:
    """Build S3/local storage key for a skill binary file."""
    return f"skills/{user_id}/{skill_name}/{file_path}"


def build_binary_ref_content(storage_key: str, mime_type: str, size: int) -> str:
    """
    Build JSON string to store in MongoDB content field for a binary file.
    """
    ref = SkillBinaryRef(
        storage_key=storage_key,
        mime_type=mime_type,
        size=size,
    )
    return json.dumps(ref.model_dump(by_alias=True))


def parse_binary_ref(content: str) -> Optional[SkillBinaryRef]:
    """
    Detect and parse a binary file reference from MongoDB content.
    Returns None if content is not a binary reference (i.e., it's regular text).
    """
    if not content or BINARY_REF_MARKER not in content:
        return None
    try:
        data = json.loads(content)
        if data.get("_binary_ref") is True:
            return SkillBinaryRef.model_validate(data)
    except (json.JSONDecodeError, Exception):
        pass
    return None


def guess_mime_type(filename: str) -> str:
    """Guess MIME type from filename."""
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or "application/octet-stream"
