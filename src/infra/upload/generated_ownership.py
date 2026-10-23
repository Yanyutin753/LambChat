"""Read ownership evidence produced by the server's reveal implementations."""

from urllib.parse import urlsplit

from src.kernel.errors import AppError


def indexed_files(row: dict, base_url: str) -> list[tuple[str, str]]:
    """Return exact uploaded keys, excluding remote echoes and inferred references."""
    from src.infra.upload.access import upload_key_from_url, validate_file_key

    key = row.get("file_key")
    if not isinstance(key, str):
        return []
    try:
        validate_file_key(key)
        if row.get("source") == "reveal_file" and key.startswith("revealed_files/"):
            path = row.get("original_path")
            url = row.get("url")
            if (
                not isinstance(path, str)
                or not path
                or urlsplit(path).scheme in ("http", "https")
                or "/api/upload/file/" in path
                or not isinstance(url, str)
                or upload_key_from_url(url, base_url) != key
            ):
                return []
            return [(key, row.get("mime_type") or "application/octet-stream")]
        if row.get("source") == "reveal_project" and key.startswith("revealed_projects/"):
            metadata = row.get("project_meta")
            if not isinstance(metadata, dict):
                return []
            files = metadata.get("files", [])
            if not isinstance(files, list):
                return []
            result = []
            for item in files:
                if not isinstance(item, dict) or not isinstance(item.get("url"), str):
                    continue
                try:
                    child = upload_key_from_url(item["url"], base_url)
                except AppError:
                    continue
                if child and child.startswith(key + "/"):
                    mime = item.get("content_type") or "text/plain"
                    result.append((child, mime))
            return result
    except (AppError, ValueError):
        return []
    return []
