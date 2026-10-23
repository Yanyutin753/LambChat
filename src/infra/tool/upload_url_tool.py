"""
URL 文件上传到沙箱工具

下载指定 URL 的文件内容，上传到沙箱文件系统的指定路径。
仅在沙箱模式下加载。

通过 ToolRuntime 注入 backend，复用 backend_utils 获取沙箱后端。
"""

import base64
import json
import re
from tempfile import SpooledTemporaryFile
from typing import Annotated, Any
from urllib.parse import quote, urlparse

import httpx
from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool, InjectedToolArg

from src.infra.async_utils import run_long_blocking_io
from src.infra.backend.lazy_sandbox import SandboxInitializationError
from src.infra.logging import get_logger
from src.infra.tool.backend_utils import (
    get_attachments_from_runtime,
    get_backend_from_runtime,
    get_base_url_from_runtime,
    get_session_id_from_runtime,
    get_user_id_from_runtime,
)
from src.infra.upload.access import authorize_file_url, require_file_access, upload_key_from_url
from src.infra.upload.file_record import get_file_record_storage
from src.kernel.errors import AppError

logger = get_logger(__name__)

# 下载超时（秒）
_DOWNLOAD_TIMEOUT = 60

# 最大文件大小（50MB，与 S3_INTERNAL_UPLOAD_MAX_SIZE 保持一致）
_MAX_FILE_SIZE = 50 * 1024 * 1024

# Keep small downloads in memory, spill larger ones to disk while enforcing _MAX_FILE_SIZE.
_SPOOL_MAX_MEMORY_BYTES = 2 * 1024 * 1024

# Legacy fallback backends only accept bytes via aupload_files(); keep that path small.
_FALLBACK_UPLOAD_MAX_BYTES = 2 * 1024 * 1024

# 本服务文件代理路径前缀（api/routes/upload.py 的 /api/upload/file/{key}）
_PROXY_URL_PREFIX = "/api/upload/file/"

# 预签名直链有效期（秒）：URL 在单次工具调用内即产即用、不落任何持久层，
# 但沙箱可能处于暂停唤醒中导致命令晚执行（E2B 恢复可达数十秒、daemon
# 排队更久），留足窗口；即便真的过期，API 侧回退会对 403 自动回落原 URL
_PRESIGN_TTL_SECONDS = 3600


async def _json_dumps_result(data: dict[str, Any]) -> str:
    return await run_long_blocking_io(json.dumps, data, ensure_ascii=False)


def _sandbox_download_command(url: str, file_path: str) -> str:
    script = f"""
import os
import urllib.request

url = {url!r}
file_path = {file_path!r}
max_size = {_MAX_FILE_SIZE!r}
chunk_size = 1024 * 1024

if file_path.startswith("../.shared/"):
    file_path = os.path.join(os.environ["LAMBCHAT_SHARED"], file_path[len("../.shared/"):])

parent = os.path.dirname(file_path)
if parent:
    os.makedirs(parent, exist_ok=True)

tmp_path = file_path + ".download_tmp"
total = 0
try:
    with urllib.request.urlopen(url, timeout={_DOWNLOAD_TIMEOUT!r}) as response:
        with open(tmp_path, "wb") as out:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_size:
                    raise RuntimeError(f"File too large: {{total}} bytes (max {{max_size}})")
                out.write(chunk)
    os.replace(tmp_path, file_path)
    print(f"LAMBCHAT_DOWNLOAD_OK {{total}}")
except Exception:
    try:
        os.remove(tmp_path)
    except FileNotFoundError:
        pass
    raise
"""
    # Base64 keeps cmd.exe expansion and POSIX quoting out of URLs and paths.
    encoded = base64.b64encode(script.encode("utf-8")).decode("ascii")
    return f"python3 -c \"import base64;exec(base64.b64decode('{encoded}'))\""


async def _resolve_storage_direct_url(
    url: str, base_url: str, *, user_id: str | None = None, session_id: str | None = None
) -> str | None:
    """把自己的文件代理 URL 就地换成对象存储预签名直链。

    沙箱下载代理 URL 要付一整跳重定向链（沙箱→API→存储 302→存储），
    E2B 实测每文件 ~1.4-1.6s 纯开销；预签名是服务端纯本地计算零网络，
    换直链后沙箱单连接直达存储。仅当 URL 是本服务裸代理路径（无查询
    参数，host 与 base_url 一致）且存储为 S3 系时生效；本地存储走
    FileResponse 直出无重定向，保持代理 URL。任何失败返回 None 走原
    URL，下载语义不变。
    """
    key = upload_key_from_url(url, base_url)
    if key is None:
        return None
    await require_file_access(key, user_id, session_id=session_id)
    if await get_file_record_storage().is_private_key(key):
        return None
    # Query variants such as thumbnails must keep their application semantics.
    if urlparse(url).query:
        return None
    try:
        from src.infra.storage.s3.service import get_or_init_storage

        storage = await get_or_init_storage()
        if storage.is_local:
            return None
        return await storage.get_presigned_url(key, _PRESIGN_TTL_SECONDS)
    except Exception as e:  # noqa: BLE001 - 解析失败不影响下载本身
        logger.info(
            "[upload_url_to_sandbox] storage_direct_url_resolved=False reason=%s",
            type(e).__name__,
        )
        return None


# 失败输出只进类别不进原文（URL/路径不得入日志，见 test_redacts_* 约定）
_FAILURE_CATEGORY_PATTERNS: tuple[tuple[str, str], ...] = (
    ("NameResolutionError", "dns"),
    ("No address associated with hostname", "dns"),
    ("timed out", "timeout"),
    ("SSLError", "tls"),
    ("CertVerificationError", "tls"),
)


def _classify_download_failure(output: str) -> str:
    """把沙箱内下载失败的 stderr/output 归类为可安全入日志的标签。"""
    match = re.search(r"HTTP Error (\d{3})", output)
    if match:
        return f"http_{match.group(1)}"
    for pattern, label in _FAILURE_CATEGORY_PATTERNS:
        if pattern in output:
            return label
    if "Traceback" in output or "Error" in output:
        return "python_exception"
    return "unknown"


async def _execute_sandbox_download(backend, url: str, file_path: str) -> tuple[bool, str]:
    resolver = getattr(backend, "aresolve_path", None)
    if not callable(resolver):
        resolver = getattr(getattr(backend, "default", None), "aresolve_path", None)
    if callable(resolver):
        file_path = await resolver(file_path)

    command = _sandbox_download_command(url, file_path)
    if hasattr(backend, "aexecute"):
        result = await backend.aexecute(command)
    elif hasattr(backend, "execute"):
        result = await run_long_blocking_io(backend.execute, command)
    else:
        return False, "backend does not support execute"

    exit_code = getattr(result, "exit_code", None)
    output = str(getattr(result, "output", "") or "")
    if exit_code == 0:
        if re.search(r"(?m)^LAMBCHAT_DOWNLOAD_OK [0-9]+\s*$", output):
            return True, "success"
        return False, "missing_download_receipt"
    # 类别而非原文入日志：沙箱内 python 的报错原文带 URL/路径（如
    # Windows daemon python3 缺失、403 拒绝），只透出可诊断的类别。
    return False, f"exit_code={exit_code} category={_classify_download_failure(output)}"


async def _session_attachments(runtime: Any, attachment_id: str = "") -> list[dict] | None:
    from src.infra.session.storage import SessionStorage
    from src.infra.session.trace_storage import TraceStorage

    user_id = get_user_id_from_runtime(runtime)
    session_id = get_session_id_from_runtime(runtime)
    if not user_id or not session_id:
        return None
    sessions = SessionStorage()
    session = await sessions.get_by_session_id(session_id) or await sessions.get_by_id(session_id)
    if not session or session.user_id != user_id or not session.is_active:
        return None
    current = [
        a
        for a in get_attachments_from_runtime(runtime) or []
        if not attachment_id or a.get("id") == attachment_id
    ]
    if attachment_id and current:
        return current
    matches: list[dict] = []
    # Strict reads include chunked history and propagate failures instead of inventing a URL.
    async for event in TraceStorage().iter_session_events_for_cleanup(
        session_id, event_types=["user:message"]
    ):
        matches.extend(
            a
            for a in (event.get("data") or {}).get("attachments", [])
            if isinstance(a, dict) and (not attachment_id or a.get("id") == attachment_id)
        )
    return matches + current


async def _resolve_attachment_url(attachment_id: str, runtime: Any, base_url: str) -> str | None:
    if not base_url:
        return None
    matches = await _session_attachments(runtime, attachment_id) or []
    keys = {a.get("key") for a in matches}
    if len(keys) != 1:
        return None
    key = keys.pop()
    if not isinstance(key, str) or "\\" in key or any(p in ("", ".", "..") for p in key.split("/")):
        return None
    record = await get_file_record_storage().find_by_key(key, get_user_id_from_runtime(runtime))
    if not record or record.get("deleting_at"):
        return None
    return f"{base_url}{_PROXY_URL_PREFIX}{quote(key, safe='/')}"


@tool
async def upload_url_to_sandbox(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    file_path: Annotated[str, "Absolute sandbox path."] = "",
    attachment_id: Annotated[str, "Uploaded file ID."] = "",
    url: Annotated[str, "External file URL."] = "",
) -> str:
    """Download attachment_id/url. No args lists session attachments."""
    if not file_path and not attachment_id and not url:
        try:
            attachments = await _session_attachments(runtime)
            if attachments is None:
                return await _json_dumps_result({"success": False, "error": "Session unavailable"})
            unique = {a["id"]: a for a in attachments if a.get("id") and a.get("key")}
            items = []
            records = get_file_record_storage()
            # shortcut: discovery lists the latest 100 IDs; add pagination if larger sessions need it.
            for item in list(unique.values())[-100:]:
                record = await records.find_by_key(item["key"], get_user_id_from_runtime(runtime))
                if record and not record.get("deleting_at"):
                    items.append({k: item[k] for k in ("id", "name", "type", "size") if k in item})
            return await _json_dumps_result(
                {"success": True, "attachments": items, "truncated": len(unique) > 100}
            )
        except Exception:
            logger.warning("[upload_url_to_sandbox] attachment_list_failed")
            return await _json_dumps_result(
                {"success": False, "error": "Attachment lookup failed; please retry later"}
            )
    if not file_path.startswith("/"):
        return await _json_dumps_result(
            {"success": False, "error": "file_path must be an absolute path"}
        )

    base_url = get_base_url_from_runtime(runtime)
    if bool(attachment_id) == bool(url):
        return await _json_dumps_result(
            {"success": False, "error": "Supply exactly one of attachment_id or url"}
        )
    if attachment_id:
        try:
            resolved_url = await _resolve_attachment_url(attachment_id, runtime, base_url)
        except Exception:
            logger.warning("[upload_url_to_sandbox] attachment_lookup_failed")
            return await _json_dumps_result(
                {"success": False, "error": "Attachment lookup failed; please retry later"}
            )
        if not resolved_url:
            return await _json_dumps_result(
                {
                    "success": False,
                    "error": "Attachment unavailable in this session; use its exact attachment ID",
                }
            )
        url = resolved_url

    # 获取 backend
    backend = get_backend_from_runtime(runtime)
    if backend is None:
        return await _json_dumps_result({"success": False, "error": "No sandbox backend available"})

    # 如果 url 是相对路径，拼接 base_url
    if url.startswith("/"):
        if base_url:
            url = f"{base_url}{url}"
        else:
            logger.warning(
                "[upload_url_to_sandbox] url_validation_failed "
                "category=relative_url_without_base_url"
            )
    # 自己的代理 URL 就地换成存储直链（省沙箱→API→存储的重定向跳），
    # 解析不出来时沿用原 URL，语义不变
    user_id = get_user_id_from_runtime(runtime)
    session_id = get_session_id_from_runtime(runtime)
    try:
        key = upload_key_from_url(url, base_url)
    except AppError:
        return await _json_dumps_result({"success": False, "error": "File unavailable"})
    if key is not None:
        records = get_file_record_storage()
        if await records.is_private_key(key):
            if not user_id or not session_id:
                return await _json_dumps_result({"success": False, "error": "File unavailable"})
            try:
                await records.require_private_access(key, user_id, session_id)
                from src.infra.storage.s3.service import get_or_init_storage

                storage = await get_or_init_storage()
                content_bytes = bytearray()
                async for chunk in storage.download_stream(key):
                    if len(content_bytes) + len(chunk) > _MAX_FILE_SIZE:
                        return await _json_dumps_result(
                            {"success": False, "error": "File too large"}
                        )
                    content_bytes.extend(chunk)
                results = await backend.aupload_files([(file_path, bytes(content_bytes))])
                if not results or results[0].error:
                    return await _json_dumps_result(
                        {"success": False, "error": "Upload failed; please retry later"}
                    )
                return await _json_dumps_result(
                    {"success": True, "path": file_path, "size": len(content_bytes)}
                )
            except SandboxInitializationError:
                raise
            except AppError:
                return await _json_dumps_result({"success": False, "error": "File unavailable"})
            except Exception:
                return await _json_dumps_result(
                    {"success": False, "error": "Download failed; please retry later"}
                )
    # The fallback must also carry authorized access when storage signing fails.
    try:
        original_url = await authorize_file_url(url, user_id, session_id, base_url=base_url)
        direct_url = await _resolve_storage_direct_url(
            url, base_url, user_id=user_id, session_id=session_id
        )
    except AppError:
        return await _json_dumps_result({"success": False, "error": "File unavailable"})
    url = original_url
    if direct_url:
        url = direct_url
        logger.info("[upload_url_to_sandbox] storage_direct_url_resolved=True")

    if hasattr(backend, "aexecute") or hasattr(backend, "execute"):
        try:
            ok, status = await _execute_sandbox_download(backend, url, file_path)
            if ok:
                logger.info("[upload_url_to_sandbox] sandbox_download_succeeded")
                return await _json_dumps_result(
                    {"success": True, "path": file_path, "source": "sandbox"}
                )
            logger.warning("[upload_url_to_sandbox] Sandbox download failed (%s)", status)
        except SandboxInitializationError:
            raise
        except Exception:
            logger.warning("[upload_url_to_sandbox] Sandbox download failed (execution_error)")

    # 下载文件。预签名直链 403（过期/签名拒绝）时回落原代理 URL 重试一次：
    # 直链只是内部加速，任何情况下不允许比直接用原 URL 更差
    content: bytes = b""
    urls_to_try = [url, original_url] if direct_url is not None else [url]
    for attempt_index, attempt_url in enumerate(urls_to_try):
        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=_DOWNLOAD_TIMEOUT
            ) as client:
                with SpooledTemporaryFile(max_size=_SPOOL_MAX_MEMORY_BYTES, mode="w+b") as spooled:
                    total_size = 0
                    async with client.stream("GET", attempt_url) as resp:
                        resp.raise_for_status()
                        async for chunk in resp.aiter_bytes():
                            if not chunk:
                                continue
                            total_size += len(chunk)
                            if total_size > _MAX_FILE_SIZE:
                                return await _json_dumps_result(
                                    {
                                        "success": False,
                                        "error": (
                                            f"File too large: {total_size} bytes "
                                            f"(max {_MAX_FILE_SIZE})"
                                        ),
                                    }
                                )
                            if total_size > _FALLBACK_UPLOAD_MAX_BYTES:
                                return await _json_dumps_result(
                                    {
                                        "success": False,
                                        "error": (
                                            "File too large for API-side fallback upload; "
                                            "use a backend with sandbox-side download support"
                                        ),
                                    }
                                )
                            await run_long_blocking_io(spooled.write, chunk)
                    await run_long_blocking_io(spooled.seek, 0)
                    content = await run_long_blocking_io(spooled.read)
            break
        except httpx.HTTPStatusError as e:
            presigned_403_retryable = (
                attempt_index == 0 and len(urls_to_try) > 1 and e.response.status_code == 403
            )
            if presigned_403_retryable:
                logger.info("[upload_url_to_sandbox] presigned_url_403_retry_original=True")
                continue
            logger.warning(
                "[upload_url_to_sandbox] download_failed category=http_status status_code=%s",
                e.response.status_code,
            )
            return await _json_dumps_result(
                {
                    "success": False,
                    "error": f"Download failed: HTTP {e.response.status_code}",
                }
            )
        except Exception as e:
            logger.warning(
                "[upload_url_to_sandbox] download_failed category=%s",
                type(e).__name__,
            )
            return await _json_dumps_result(
                {"success": False, "error": "Download failed; please retry later"}
            )

    # 上传到沙箱
    try:
        results = await backend.aupload_files([(file_path, content)])
        result = results[0]
        if result.error:
            return await _json_dumps_result(
                {"success": False, "error": "Upload failed; please retry later"}
            )
        logger.info(
            "[upload_url_to_sandbox] upload_succeeded size_bytes=%s",
            len(content),
        )
        return await _json_dumps_result({"success": True, "path": file_path, "size": len(content)})
    except Exception as e:
        logger.error(
            "[upload_url_to_sandbox] upload_failed category=%s",
            type(e).__name__,
        )
        return await _json_dumps_result(
            {"success": False, "error": "Upload failed; please retry later"}
        )


def get_upload_url_tool() -> BaseTool:
    """获取 upload_url_to_sandbox 工具实例"""
    return upload_url_to_sandbox
