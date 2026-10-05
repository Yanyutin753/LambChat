"""Project bundle shell command and bounded in-memory archive parsing."""

import io
import posixpath
import shlex
import tarfile

from src.infra.logging import get_logger

logger = get_logger(__name__)

# Bound both downloaded archives and extracted file buffers.
BUNDLE_EXTRACT_TOTAL_LIMIT = 256 * 1024 * 1024


def _build_bundle_command(project_path: str, bundle_path: str, selected_paths: list[str]) -> str:
    """仅打包筛选后的文件；文件变为目录时也不递归扩大扫描范围。"""
    parts = ["tar", "czf", bundle_path, "--no-recursion", "-C", project_path, "--"]
    for rel_path in selected_paths:
        normalized = posixpath.normpath(rel_path.lstrip("/"))
        if normalized in {".", ".."} or normalized.startswith("../"):
            raise ValueError(f"Invalid bundle member path: {rel_path}")
        parts.append(f"./{normalized}")
    return shlex.join(parts)


def _extract_bundle_members(
    bundle_bytes: bytes,
    wanted: set[str],
    *,
    max_member_size: int | None = None,
    max_total_size: int = BUNDLE_EXTRACT_TOTAL_LIMIT,
) -> dict[str, bytes] | None:
    """安全解包 bundle，只保留 wanted 清单里的普通文件。

        - 路径清洗后拒绝绝对路径与 ``..`` 上溯（tar 路径穿越）；
    - 非 UTF-8 文件名、非普通文件成员跳过；
        - 单成员超过 ``max_member_size`` 跳过（与逐文件路径的超限语义一致）；
        - 解包总量超过 ``BUNDLE_EXTRACT_TOTAL_LIMIT`` 返回 None（调用方整体降级
          逐文件路径——那条路径逐文件流转，不驻留大内存）。
    """
    members: dict[str, bytes] = {}
    total = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(bundle_bytes), mode="r:gz") as tf:
            for member in tf:
                if not member.isreg():
                    continue
                normalized = posixpath.normpath(member.name)
                if (
                    not normalized
                    or normalized == "."
                    or normalized.startswith("/")
                    or normalized == ".."
                    or normalized.startswith("../")
                ):
                    continue
                rel_path = f"/{normalized}"
                if rel_path not in wanted:
                    continue
                if max_member_size is not None and member.size > max_member_size:
                    continue
                total += member.size
                if total > max_total_size:
                    logger.info(
                        f"bundle extraction exceeds total limit {max_total_size}, "
                        "falling back to per-file upload"
                    )
                    return None
                try:
                    normalized.encode("utf-8")
                except UnicodeEncodeError:
                    continue
                extracted = tf.extractfile(member)
                if extracted is None:
                    continue
                members[rel_path] = extracted.read()
    except (tarfile.TarError, OSError, EOFError) as e:
        logger.info(f"bundle extraction failed: {e}")
        return None
    return members
