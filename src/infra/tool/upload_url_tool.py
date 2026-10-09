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
from urllib.parse import unquote, urlparse

import httpx
from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool, InjectedToolArg

from src.infra.async_utils import run_long_blocking_io
from src.infra.backend.lazy_sandbox import SandboxInitializationError
from src.infra.logging import get_logger
from src.infra.tool.backend_utils import get_backend_from_runtime, get_base_url_from_runtime

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
    print(total)
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


async def _resolve_storage_direct_url(url: str, base_url: str) -> str | None:
    """把自己的文件代理 URL 就地换成对象存储预签名直链。

    沙箱下载代理 URL 要付一整跳重定向链（沙箱→API→存储 302→存储），
    E2B 实测每文件 ~1.4-1.6s 纯开销；预签名是服务端纯本地计算零网络，
    换直链后沙箱单连接直达存储。仅当 URL 是本服务裸代理路径（无查询
    参数，host 与 base_url 一致）且存储为 S3 系时生效；本地存储走
    FileResponse 直出无重定向，保持代理 URL。任何失败返回 None 走原
    URL，下载语义不变。
    """
    try:
        parsed = urlparse(url)
        if not parsed.path.startswith(_PROXY_URL_PREFIX) or parsed.query:
            return None
        if not base_url or parsed.netloc != urlparse(base_url).netloc:
            return None
        key = unquote(parsed.path[len(_PROXY_URL_PREFIX) :])
        if not key:
            return None

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

    exit_code = getattr(result, "exit_code", 0)
    if exit_code == 0:
        return True, "success"
    # 类别而非原文入日志：沙箱内 python 的报错原文带 URL/路径（如
    # Windows daemon python3 缺失、403 拒绝），只透出可诊断的类别。
    output = str(getattr(result, "output", "") or "")
    return False, f"exit_code={exit_code} category={_classify_download_failure(output)}"


@tool
async def upload_url_to_sandbox(
    url: Annotated[str, "URL of the file to download."],
    file_path: Annotated[str, "Absolute target file path inside the sandbox."],
    runtime: Annotated[ToolRuntime, InjectedToolArg],
) -> str:
    """Download a URL to a sandbox file path for use by shell commands and scripts."""
    if not file_path.startswith("/"):
        return await _json_dumps_result(
            {"success": False, "error": "file_path must be an absolute path"}
        )

    # 获取 backend
    backend = get_backend_from_runtime(runtime)
    if backend is None:
        return await _json_dumps_result({"success": False, "error": "No sandbox backend available"})

    # 如果 url 是相对路径，拼接 base_url
    base_url = get_base_url_from_runtime(runtime)
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
    original_url = url
    direct_url = await _resolve_storage_direct_url(url, base_url)
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
