"""ZIP parsing helpers for the Skills API."""

import io
import re
import zipfile

from src.api.routes.upload import get_s3_enabled
from src.infra.skill.binary import is_binary_file
from src.kernel.config import settings

_ZIP_MEMBER_MAX_BYTES: int | None = None
_ZIP_MAX_MEMBERS = 500


def _zip_member_should_skip(name: str) -> bool:
    return (
        name.endswith("/")
        or "__MACOSX" in name
        or name.endswith(".DS_Store")
        or name.endswith("Thumbs.db")
        or ".git/" in name
    )


def _strip_single_top_level_prefix(names: list[str]) -> str:
    top_level = set()
    for name in names:
        parts = name.split("/")
        if parts[0]:
            top_level.add(parts[0])
    if len(top_level) != 1:
        return ""
    top = next(iter(top_level))
    return f"{top}/" if any(name.startswith(f"{top}/") for name in names) else ""


def _normalize_zip_member_path(name: str, prefix: str) -> str | None:
    normalized_name = name.replace("\\", "/")
    if (
        normalized_name.startswith("/")
        or re.match(r"^[A-Za-z]:/", normalized_name)
        or ".." in normalized_name.split("/")
    ):
        raise ValueError(f"Unsafe ZIP member path: {name}")
    if prefix:
        if not normalized_name.startswith(prefix):
            return None
        normalized_name = normalized_name[len(prefix) :]
    if not normalized_name:
        return None
    if (
        normalized_name.startswith("/")
        or re.match(r"^[A-Za-z]:/", normalized_name)
        or ".." in normalized_name.split("/")
    ):
        raise ValueError(f"Unsafe ZIP member path: {name}")
    return normalized_name


def _normalize_skill_file_path(path: str) -> str:
    parts = path.replace("\\", "/").split("/")
    if parts and parts[-1].lower() == "skill.md":
        parts[-1] = "SKILL.md"
    return "/".join(parts)


def _get_skill_upload_max_size() -> tuple[int, int]:
    if get_s3_enabled():
        max_size_bytes = int(settings.S3_MAX_FILE_SIZE)
    else:
        max_size_bytes = int(settings.FILE_UPLOAD_MAX_SIZE_DOCUMENT) * 1024 * 1024
    return max_size_bytes, max_size_bytes // (1024 * 1024)


def _parse_skill_name_description(skill_md_content: str, fallback_name: str) -> tuple[str, str]:
    skill_name = None
    description = ""
    if skill_md_content:
        try:
            from src.infra.skill.parser import (
                parse_skill_md,
                sanitize_skill_name,
            )

            parsed_name, parsed_desc, _ = parse_skill_md(skill_md_content)
            if parsed_name:
                skill_name = sanitize_skill_name(parsed_name)
            if parsed_desc:
                description = parsed_desc
        except Exception:
            pass
    if not skill_name and fallback_name:
        skill_name = fallback_name.split("/")[-1]
    return skill_name or "unnamed-skill", description


def _validate_zip_upload(zip_content: bytes) -> tuple[zipfile.ZipFile, list[zipfile.ZipInfo], int]:
    max_file_size, _max_file_size_mb = _get_skill_upload_max_size()
    if len(zip_content) > max_file_size:
        raise ValueError("ZIP file too large")

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_content))
    except zipfile.BadZipFile:
        raise ValueError("Invalid ZIP file")

    try:
        infos = zf.infolist()
        if len(infos) > _ZIP_MAX_MEMBERS:
            raise ValueError(f"ZIP contains too many files (max {_ZIP_MAX_MEMBERS})")

        total_uncompressed_size = sum(info.file_size for info in infos)
        if total_uncompressed_size > max_file_size:
            max_file_size_mb = max_file_size // (1024 * 1024)
            raise ValueError(f"ZIP uncompressed content too large (max {max_file_size_mb}MB)")
        return zf, infos, max_file_size
    except Exception:
        zf.close()
        raise


def _parse_zip_skill_preview(zip_content: bytes) -> list[dict]:
    zf, infos, max_file_size = _validate_zip_upload(zip_content)
    try:
        names = [info.filename for info in infos]
        info_by_name = {info.filename: info for info in infos}
        prefix = _strip_single_top_level_prefix(names)
        member_max_size = _ZIP_MEMBER_MAX_BYTES or max_file_size
        valid_paths: list[str] = []
        binary_paths: set[str] = set()
        skill_md_by_path: dict[str, str] = {}

        for name in names:
            if _zip_member_should_skip(name):
                continue
            rel_path = _normalize_zip_member_path(name, prefix)
            if not rel_path:
                continue
            info = info_by_name.get(name)
            if info and info.file_size > member_max_size:
                raise ValueError(
                    f"ZIP member too large: {name} "
                    f"({info.file_size} bytes, max {member_max_size} bytes)"
                )
            rel_path = _normalize_skill_file_path(rel_path)
            valid_paths.append(rel_path)
            if is_binary_file(rel_path):
                binary_paths.add(rel_path)
            if rel_path.split("/")[-1].lower() == "skill.md":
                try:
                    skill_md_by_path[rel_path] = zf.read(name).decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise ValueError(f"SKILL.md must be UTF-8 text: {rel_path}") from exc

        if not skill_md_by_path:
            raise ValueError("No SKILL.md found in ZIP")

        previews: list[dict] = []
        for skill_md_path, skill_md_content in skill_md_by_path.items():
            skill_root = skill_md_path.rsplit("/", 1)[0] if "/" in skill_md_path else ""
            skill_prefix = skill_root + "/" if skill_root else ""
            files = [
                path[len(skill_prefix) :]
                for path in valid_paths
                if path.startswith(skill_prefix) and path[len(skill_prefix) :]
            ]
            if not files:
                continue
            skill_name, description = _parse_skill_name_description(
                skill_md_content,
                skill_root,
            )
            binary_files = sorted(
                path[len(skill_prefix) :]
                for path in binary_paths
                if path.startswith(skill_prefix) and path[len(skill_prefix) :]
            )
            previews.append(
                {
                    "name": skill_name,
                    "description": description,
                    "file_count": len(files),
                    "files": sorted(files),
                    "binary_files": binary_files,
                }
            )

        if not previews:
            raise ValueError("No valid skills found in ZIP")
        return previews
    finally:
        zf.close()


def _parse_zip_skills(
    zip_content: bytes,
) -> list[tuple[str, dict[str, str], dict[str, bytes]]]:
    """
    解析 ZIP 内容，找到所有 SKILL.md 文件，每个 SKILL.md 的上级文件夹作为一个独立 skill。

    Returns:
        list of (skill_name, text_files_dict, binary_files_dict) tuples
    """
    zf, infos, max_file_size = _validate_zip_upload(zip_content)
    try:
        names = [info.filename for info in infos]
        info_by_name = {info.filename: info for info in infos}
        member_max_size = _ZIP_MEMBER_MAX_BYTES or max_file_size

        # 检测并去掉单顶层目录前缀（如 awesome-claude-skills/xxx → xxx）
        prefix = _strip_single_top_level_prefix(names)

        # 读取所有有效文件，区分文本和二进制
        text_files: dict[str, str] = {}
        binary_files: dict[str, bytes] = {}
        for name in names:
            if _zip_member_should_skip(name):
                continue
            info = info_by_name.get(name)
            if info and info.file_size > member_max_size:
                raise ValueError(
                    f"ZIP member too large: {name} "
                    f"({info.file_size} bytes, max {member_max_size} bytes)"
                )
            try:
                raw = zf.read(name)
            except Exception:
                continue

            # 检测二进制文件
            if is_binary_file(name, raw):
                binary_files[name] = raw
            else:
                try:
                    text = raw.decode("utf-8")
                    text_files[_normalize_skill_file_path(name)] = text
                except UnicodeDecodeError:
                    # 即使通过了扩展名检查，UTF-8 解码失败也当二进制
                    binary_files[name] = raw

        # 去掉顶层目录前缀
        if prefix:
            text_files = {
                _normalize_skill_file_path(normalized): content
                for key, content in text_files.items()
                if (normalized := _normalize_zip_member_path(key, prefix))
            }
            binary_files = {
                normalized: data
                for key, data in binary_files.items()
                if (normalized := _normalize_zip_member_path(key, prefix))
            }

        # 找到所有 SKILL.md 的路径
        skill_md_paths = [p for p in text_files.keys() if p.split("/")[-1].lower() == "skill.md"]

        if not skill_md_paths:
            raise ValueError("No SKILL.md found in ZIP")

        skills: list[tuple[str, dict[str, str], dict[str, bytes]]] = []

        for skill_md_path in skill_md_paths:
            # SKILL.md 所在的文件夹就是 skill 的根目录
            skill_root = skill_md_path.rsplit("/", 1)[0] if "/" in skill_md_path else ""
            skill_prefix = skill_root + "/" if skill_root else ""

            # 收集该 skill 根目录下的所有文件（相对路径）
            skill_text_files: dict[str, str] = {}
            for fpath, content in text_files.items():
                if fpath.startswith(skill_prefix):
                    rel = fpath[len(skill_prefix) :]
                    if rel:
                        skill_text_files[rel] = content

            skill_binary_files: dict[str, bytes] = {}
            for fpath, data in binary_files.items():
                if fpath.startswith(skill_prefix):
                    rel = fpath[len(skill_prefix) :]
                    if rel:
                        skill_binary_files[rel] = data

            # 优先使用 SKILL.md 的 name 字段，回退到文件夹名
            skill_md_content = skill_text_files.get("SKILL.md", "")
            skill_name, _description = _parse_skill_name_description(skill_md_content, skill_root)

            if skill_text_files or skill_binary_files:
                skills.append((skill_name, skill_text_files, skill_binary_files))

        if not skills:
            raise ValueError("No valid skills found in ZIP")

        return skills
    finally:
        zf.close()
