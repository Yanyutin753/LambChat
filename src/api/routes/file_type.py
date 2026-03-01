"""File type classification utilities"""

from enum import Enum
from typing import Optional


class FileCategory(str, Enum):
    """File category enum"""

    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    UNKNOWN = "unknown"


# File extension mappings
FILE_EXTENSIONS: dict[FileCategory, set[str]] = {
    FileCategory.IMAGE: {"jpg", "jpeg", "png", "gif", "webp", "svg", "bmp", "ico"},
    FileCategory.VIDEO: {"mp4", "webm", "mov", "avi", "mkv", "wmv", "flv"},
    FileCategory.AUDIO: {"mp3", "wav", "ogg", "aac", "flac", "m4a", "wma"},
    FileCategory.DOCUMENT: {
        "pdf",
        "doc",
        "docx",
        "xls",
        "xlsx",
        "ppt",
        "pptx",
        "txt",
        "md",
        "csv",
        "rtf",
    },
}

# MIME type prefixes
MIME_TYPE_PREFIXES: dict[FileCategory, str] = {
    FileCategory.IMAGE: "image/",
    FileCategory.VIDEO: "video/",
    FileCategory.AUDIO: "audio/",
}


def get_file_category(filename: str, mime_type: Optional[str] = None) -> FileCategory:
    """
    Determine file category from filename and MIME type

    Args:
        filename: Original filename
        mime_type: Optional MIME type from upload

    Returns:
        FileCategory enum value
    """
    # Try MIME type first
    if mime_type:
        for category, prefix in MIME_TYPE_PREFIXES.items():
            if mime_type.startswith(prefix):
                return category
        # Handle specific MIME types
        if mime_type == "application/pdf":
            return FileCategory.DOCUMENT
        if mime_type.startswith("application/msword") or mime_type.startswith("application/vnd."):
            return FileCategory.DOCUMENT

    # Fall back to extension
    ext = filename.lower().split(".")[-1] if "." in filename else ""
    for category, extensions in FILE_EXTENSIONS.items():
        if ext in extensions:
            return category

    return FileCategory.UNKNOWN


def get_permission_for_category(category: FileCategory) -> Optional[str]:
    """Get permission required for a file category"""
    mapping = {
        FileCategory.IMAGE: "file:upload:image",
        FileCategory.VIDEO: "file:upload:video",
        FileCategory.AUDIO: "file:upload:audio",
        FileCategory.DOCUMENT: "file:upload:document",
    }
    return mapping.get(category)
