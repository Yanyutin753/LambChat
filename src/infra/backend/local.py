"""本地沙箱后端：命令经中继落到用户本机 daemon 执行（spec §3.3）。

文件操作（ls/read/write/edit/glob/grep）由 deepagents BaseSandbox 基于
execute()/aexecute() 自动继承，无需在本类重写；upload/download 是
BaseSandbox 的抽象成员，这里以单条 python3 + base64 命令往返实现，
仍走同一条中继链路（daemon 协议在 M1 仅有 exec 一个 op）。

平台分支（M4 T3）：daemon 经 connect URL 上报平台（注册表 value 第三段），
本后端每次 upload/download 操作前查一次活跃 daemon 的平台——win32 时命令
生成改用 cmd.exe 引用（:func:`_cmd_quote`，与 client platform.py 同则互锁）、
省略 ``mkdir -p`` 前缀（makedirs 并进脚本）、脚本单行化且无 ``%``；
其余（含无平台信息）保持 posix 现状，命令串逐字节不变。

注意（与 E2BBackend 相反的方向）：本后端的原生原语是异步的
（dispatch_local_call 轮询 Redis），因此 aexecute 是主路径，同步
execute 通过 asyncio.run 桥接（照 _skills_path_utils._run_async 模式）；
run_blocking_io 接收同步可调用对象，无法用于这里的异步→同步桥接。
"""

import asyncio
import base64
import posixpath
import re
import shlex
from dataclasses import dataclass
from typing import Any, Coroutine, TypeVar, cast

from deepagents.backends.protocol import ASYNC_GLOB_TIMEOUT
from deepagents.backends.sandbox import BaseSandbox, _build_glob_cmd, _parse_glob_output

from src.infra.backend.protocol_compat import (
    DeleteResult,
    EditResult,
    ExecuteResponse,
    ExtendedFileError,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GlobResult,
    GrepResult,
    LsResult,
    WriteResult,
    file_download_response,
    file_upload_response,
)
from src.infra.logging import get_logger
from src.infra.sandbox.relay.dispatch import dispatch_local_call
from src.infra.sandbox.relay.registry import SandboxClientRegistry
from src.kernel.config import settings
from src.kernel.errors import AppError

logger = get_logger(__name__)

T = TypeVar("T")

# 上传分块阈值：单条命令的原始内容上限 48KB（b64 后 ~64KB）。
# b64 内容作为单个 argv 下发，内核 MAX_ARG_STRLEN 限制单参数 128KB，
# 扣除引号/命令前缀开销后 ~96KB 即触发 E2BIG（Errno 7）——48KB 留足余量。
_UPLOAD_CHUNK_RAW_BYTES = 48 * 1024

# 下载单文件上限 2MB：与服务端 SANDBOX_RESULTS_MAX_BYTES（2 MiB）同量级。
# 无预检时超限文件会整读 base64 回传，轻则链路中途炸出含糊错误、重则撑爆
# results 回传 body——stat 预检在 daemon 侧给显式 file_too_large 而非 base64。
_DOWNLOAD_MAX_BYTES = 2 * 1024 * 1024


# =========================================================================
# 文件命令生成的平台分支（M4 T3）
# =========================================================================


def _cmd_quote(s: str) -> str:
    """Windows cmd.exe 参数引用：与 client ``platform._quote_windows`` 完全同则。

    规则出处（微软 cmdline 解析文档 "Parsing C++ command-line arguments"，
    learn.microsoft.com/en-us/cpp/c-language/parsing-c-command-line-arguments）：

    - 规则 2：双引号包裹的字符串被解析为单个参数，其中的空白不断词；
    - 规则 4：反斜杠仅当紧邻双引号时才有转义含义，其余场合按字面量；
    - 规则 5/6（引号/反斜杠交互）：引号前有 N 个反斜杠——N 为偶数时 N/2 个
      是字面量、该引号作字符串定界符；N 为奇数时 (N-1)/2 个是字面量、且该
      引号本身是字面引号。

    据此把任意参数编码为安全命令行片段：外层始终双引号包裹；参数内每个字面
    ``"`` 前置 ``2N+1`` 个反斜杠（N 为其前紧邻的字面反斜杠数——先加倍原有
    反斜杠，再补一个转义引号的反斜杠）；收尾引号前若有 N 个字面反斜杠，加倍
    为 2N（否则按规则 5 会被吃掉一半并提前闭合引号）。双侧（client/platform.py
    与本函数）用同一组 torture 用例单测互锁，防规则漂移。

    与 client 版的**有意差异**：daemon 的 Windows 执行器是 ``shell=True`` 经
    cmd.exe，双引号内 ``%VAR%`` 仍会被环境变量展开，而命令行上下文（非
    batch 文件）没有可靠的 ``%`` 转义（``%%`` 只在 batch 生效）——含 ``%``
    的参数退化为**拒绝**（ValueError），由 ``_upload_one``/``download_files``
    的既有兜底映射为文件错误，杜绝静默注入/静默错路径。
    """
    if "%" in s:
        raise ValueError(f"argument contains '%' which cannot be safely quoted for cmd.exe: {s!r}")
    out: list[str] = ['"']
    backslashes = 0
    for ch in s:
        if ch == "\\":
            backslashes += 1
            continue
        if ch == '"':
            # 字面引号前置 2N+1 个反斜杠（规则 5/6 的逆向编码）
            out.append("\\" * (backslashes * 2 + 1))
            out.append('"')
        else:
            # 不紧邻引号的反斜杠是字面量（规则 4），按原样透传
            out.append("\\" * backslashes)
            out.append(ch)
        backslashes = 0
    # 收尾引号前的 N 个字面反斜杠加倍为 2N，避免被解析成“转义掉闭合引号”
    out.append("\\" * (backslashes * 2))
    out.append('"')
    return "".join(out)


@dataclass(frozen=True)
class _PlatformCmdCtx:
    """文件命令生成的平台分支上下文。

    - posix（含空/未知/darwin/linux）：现状——shlex.quote 引用、shell 侧
      ``mkdir -p`` 前缀、``python3`` 解释器；
    - win32（daemon 上报）：``_cmd_quote`` cmd 引用、mkdir 前缀省略（makedirs
      并进 python 脚本——cmd.exe 无 ``mkdir -p``，多级父目录创建在 python 里
      幂等）、``python3`` 不变（daemon 侧 PATH 有内嵌 shim，M4 T4）。
    """

    is_windows: bool

    def quote(self, s: str) -> str:
        """单个参数的 shell 引用：posix→shlex，win32→cmd 双引号规则。"""
        return _cmd_quote(s) if self.is_windows else shlex.quote(s)

    def mkdir_prefix(self, parent: str, *, append: bool) -> str:
        """首块上传的父目录创建前缀：win32 省略（makedirs 在脚本内），posix 现状。

        追加块父目录必已存在（首块已建），两者都不建。
        """
        if self.is_windows or not parent or append:
            return ""
        return f"mkdir -p {shlex.quote(parent)} && "


def _platform_ctx(platform: str) -> _PlatformCmdCtx:
    """按 daemon 上报平台取命令生成上下文。

    只有 win32/windows 走 Windows 分支；其余任何值（空串=未上报/旧格式 value、
    linux/darwin、未知串）一律 posix——「无平台信息 → 现状零变化」。
    """
    return _PlatformCmdCtx(is_windows=platform in ("win32", "windows"))


async def _lookup_daemon_platform(user_id: str) -> str:
    """经注册表查当前活跃 daemon 的上报平台（win32/linux/darwin）。

    一次 redis 读（注册表 value 第三段，M4 T3）；离线/旧格式/未上报返回
    空串，任何故障（redis 不可达等）也回落空串——空串在 :func:`_platform_ctx`
    归一为 posix，文件操作不因平台查询失败而中断。
    """
    try:
        return await SandboxClientRegistry().get_platform(user_id)
    except Exception:  # noqa: BLE001 - 平台查询尽力而为，失败回落 posix
        logger.warning("daemon platform lookup failed for user %s; falling back to posix", user_id)
        return ""


def _run_coro_sync(coro: Coroutine[Any, Any, T]) -> T:
    """在同步上下文中运行异步协程（照 _skills_path_utils._run_async 模式）。

    没有运行中的事件循环（如 asyncio.to_thread 的 worker 线程）时用
    asyncio.run；若在运行中的事件循环内被同步调用则报错，要求改用异步 API。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    coro.close()
    raise RuntimeError(
        "LocalSandboxBackend.execute() cannot run inside an active event loop; use aexecute()."
    )


def _classify_file_error(text: str) -> ExtendedFileError:
    """把 daemon 返回的错误文本映射为标准 FileOperationError 字面量。

    ENOENT 的真实输出（`[Errno 2] No such file or directory: '...'`）包含
    "directory" 子串，必须先于 is-a-directory 判定，否则误分类；errno 编号
    用 `]` 收尾匹配，避免 "errno 2" 撞上 "errno 21" 的前缀。
    """
    lowered = text.lower()
    if "no such file" in lowered or "errno 2]" in lowered:
        return "file_not_found"
    if "permission" in lowered:
        return "permission_denied"
    if "is a directory" in lowered or "errno 21]" in lowered or "eisdir" in lowered:
        return "is_directory"
    # E2BIG（Errno 7，argv 超长）/ EFBIG（Errno 27）/ 显式超限文本（下载预检）
    if (
        "too large" in lowered
        or "too_large" in lowered
        or "argument list too long" in lowered
        or "errno 7]" in lowered
        or "e2big" in lowered
    ):
        return "file_too_large"
    return "file_not_found"


class LocalSandboxBackend(BaseSandbox):
    """本地沙箱后端：命令经中继（Redis 请求/结果通道）落到用户本机 daemon。

    cwd 固定为 `/workspace/{session_id}`（spec §3.3），由 daemon 负责创建与
    切换；执行超时默认取 settings.SANDBOX_LOCAL_EXEC_TIMEOUT。
    """

    def __init__(
        self,
        *,
        user_id: str,
        session_id: str,
        exec_timeout: int | None = None,
        platform_hint: str | None = None,
    ):
        self._user_id = user_id
        self._session_id = session_id
        self._exec_timeout = exec_timeout or settings.SANDBOX_LOCAL_EXEC_TIMEOUT
        # 显式平台提示（构造期已知 daemon 平台的 wiring/测试用）；None = 每次
        # 文件操作前经注册表查当前活跃 daemon 的平台（一次 redis 读）。
        self._platform_hint = platform_hint

    async def _resolve_platform(self) -> str:
        """本次命令生成所用平台：显式 hint 优先，否则查注册表（容错 posix）。"""
        if self._platform_hint is not None:
            return self._platform_hint
        return await _lookup_daemon_platform(self._user_id)

    @property
    def id(self) -> str:
        return f"local-{self._session_id}"

    @property
    def work_dir(self) -> str:
        """沙箱工作目录（daemon 侧 cwd 契约，spec §3.3，与 aexecute 的 cwd 一致）。

        create_sandbox_backend 以 getattr(backend, "work_dir") 锚定 artifacts 根，
        缺失会退化到云端默认 "/home/user"，在用户本机上不存在。
        """
        return f"/workspace/{self._session_id}"

    async def before_tool_start(self, tool_name: str, tool_input: dict[str, object]) -> None:
        """LazySandboxBackend 同名契约的对等实现（agent_node 事件处理器 wiring）。

        本地 daemon 常驻用户机器，无需懒初始化与生命周期事件，空实现即可。
        """
        del tool_name, tool_input

    # =========================================================================
    # Command execution（BaseSandbox 的抽象成员，其余文件操作由此自动继承）
    # =========================================================================

    async def aexecute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        result = await dispatch_local_call(
            self._user_id,
            "exec",
            {"command": command, "cwd": self.work_dir},
            timeout=float(timeout or self._exec_timeout),
        )
        stdout = result.get("stdout") or ""
        stderr = result.get("stderr") or ""
        # ExecuteResponse 只有合并 output 字段（protocol.py），照 E2BBackend 的拼接方式
        output = f"{stdout}\n{stderr}" if stdout and stderr else (stdout or stderr)
        exit_code = result.get("exit_code")
        # 缺失 exit_code 透传 None（协议：未确定），不伪装成 0 成功
        return ExecuteResponse(
            output=output,
            exit_code=int(exit_code) if exit_code is not None else None,
            truncated=False,
        )

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        return _run_coro_sync(self.aexecute(command, timeout=timeout))

    # =========================================================================
    # Upload / download（BaseSandbox 抽象成员，经 exec op 的单命令往返实现）
    # =========================================================================

    @staticmethod
    def _upload_command(
        path: str, content: bytes, *, append: bool = False, platform: str = ""
    ) -> str:
        ctx = _platform_ctx(platform)
        mode = "ab" if append else "wb"
        parent = posixpath.dirname(path)
        b64_content = base64.standard_b64encode(content).decode("ascii")
        if ctx.is_windows:
            # win32：无 mkdir 前缀——首块把 os.makedirs 并进脚本（parent 从
            # argv[1] 现场推导，正/反斜杠与绝对/相对路径都按 daemon 本机
            # os.path 语义处理）；引用走 cmd 双引号规则；脚本保持单行
            # （cmd.exe 逐行解析，多行 python -c 会在换行处截断）。
            makedirs = (
                "d = os.path.dirname(sys.argv[1]); os.makedirs(d, exist_ok=True) if d else None; "
                if not append
                else ""
            )
            imports = "import base64, os, sys; " if makedirs else "import base64, sys; "
            return (
                f'python3 -c "{imports}{makedirs}'
                f"open(sys.argv[1], '{mode}').write(base64.b64decode(sys.argv[2]))\" "
                f"{_cmd_quote(path)} {_cmd_quote(b64_content)}"
            )
        # posix：与既有字节形态完全一致（mkdir -p 前缀 + shlex 引用）
        mkdir = ctx.mkdir_prefix(parent, append=append)
        return (
            f'{mkdir}python3 -c "import base64, sys; '
            f"open(sys.argv[1], '{mode}').write(base64.b64decode(sys.argv[2]))\" "
            f"{shlex.quote(path)} {shlex.quote(b64_content)}"
        )

    @classmethod
    def _upload_chunk_commands(cls, path: str, content: bytes, *, platform: str = "") -> list[str]:
        """上传命令序列：≤48KB 单命令直写；更大分块——首块 `wb` 截断创建，后续块 `ab` 追加。

        整个 b64 塞单个 argv 会撞内核 MAX_ARG_STRLEN（E2BIG，见
        _UPLOAD_CHUNK_RAW_BYTES 注释），分片后每条命令的 argv 都留足余量。
        """
        if len(content) <= _UPLOAD_CHUNK_RAW_BYTES:
            return [cls._upload_command(path, content, platform=platform)]
        commands = [cls._upload_command(path, content[:_UPLOAD_CHUNK_RAW_BYTES], platform=platform)]
        for offset in range(_UPLOAD_CHUNK_RAW_BYTES, len(content), _UPLOAD_CHUNK_RAW_BYTES):
            commands.append(
                cls._upload_command(
                    path,
                    content[offset : offset + _UPLOAD_CHUNK_RAW_BYTES],
                    append=True,
                    platform=platform,
                )
            )
        return commands

    @staticmethod
    def _download_command(path: str, *, platform: str = "") -> str:
        ctx = _platform_ctx(platform)
        if ctx.is_windows:
            # win32：单行脚本（cmd.exe 逐行解析）；错误消息不用 % 格式化——
            # cmd 在双引号内展开 %VAR%，两个 % 定界即被吞改，改用字符串拼接；
            # 超限短路退出（`and` 短路 + sys.exit）与 posix 分支同语义。
            script = (
                "import os, sys, base64; "
                "size = os.path.getsize(sys.argv[1]); "
                f"size > {_DOWNLOAD_MAX_BYTES} and (sys.stderr.write("
                f"'file_too_large: ' + str(size) + ' bytes exceeds {_DOWNLOAD_MAX_BYTES} limit"
                " (download cap)'), sys.exit(1)); "
                "sys.stdout.buffer.write(base64.b64encode(open(sys.argv[1], 'rb').read()))"
            )
            return f'python3 -c "{script}" {ctx.quote(path)}'
        # stat 预检：超限打印显式 error（exit 1，stderr 带 file_too_large 标记与
        # 字节数）而非输出 base64；不存在的路径仍由 python 抛 ENOENT 走原分类。
        script = (
            "import os, sys, base64\n"
            "size = os.path.getsize(sys.argv[1])\n"
            f"if size > {_DOWNLOAD_MAX_BYTES}:\n"
            f"    sys.stderr.write('file_too_large: %d bytes exceeds {_DOWNLOAD_MAX_BYTES} limit'\n"
            "                  ' (download cap)')\n"
            "    sys.exit(1)\n"
            "sys.stdout.buffer.write(base64.b64encode(open(sys.argv[1], 'rb').read()))"
        )
        return f'python3 -c "{script}" {ctx.quote(path)}'

    def _upload_one(self, path: str, content: bytes, *, platform: str = "") -> FileUploadResponse:
        try:
            for command in self._upload_chunk_commands(path, content, platform=platform):
                result = self.execute(command)
                if result.exit_code != 0:
                    return self._upload_response(path, result)
        except AppError:
            # 中继级故障（离线/超时）不属于单文件错误，向上透传给统一错误处理
            raise
        except Exception:
            # 含 win32 分支对 % 路径的拒绝（_cmd_quote ValueError）：命令尚未
            # 下发，落进本兜底映射为 invalid_path
            logger.exception("local upload_files(%s) failed", path)
            return file_upload_response(path=path, error="invalid_path")
        return FileUploadResponse(path=path, error=None)

    async def _aupload_one(
        self, path: str, content: bytes, *, platform: str = ""
    ) -> FileUploadResponse:
        try:
            for command in self._upload_chunk_commands(path, content, platform=platform):
                result = await self.aexecute(command)
                if result.exit_code != 0:
                    return self._upload_response(path, result)
        except AppError:
            raise
        except Exception:
            logger.exception("local aupload_files(%s) failed", path)
            return file_upload_response(path=path, error="invalid_path")
        return FileUploadResponse(path=path, error=None)

    def _upload_response(self, path: str, result: ExecuteResponse) -> FileUploadResponse:
        if result.exit_code != 0:
            return file_upload_response(
                path=path,
                error=_classify_file_error(result.output),
            )
        return FileUploadResponse(path=path, error=None)

    def _download_response(self, path: str, result: dict) -> FileDownloadResponse:
        """从 dispatch 原始结果构造下载响应：内容只取 stdout（base64），stderr 不混入。"""
        if result.get("exit_code") != 0:
            error_text = "\n".join(x for x in (result.get("stdout"), result.get("stderr")) if x)
            return file_download_response(
                path=path, content=None, error=_classify_file_error(error_text)
            )
        stdout = (result.get("stdout") or "").strip()
        try:
            content = base64.b64decode(stdout)
        except (ValueError, TypeError):
            # 解码失败 ≠ 文件不存在：错误带原始 stdout 片段供排查，不误报 file_not_found
            logger.warning("local download_files(%s) got non-base64 output", path)
            return file_download_response(
                path=path,
                content=None,
                error=f"invalid_download_output: {stdout[:80]!r}",
            )
        return FileDownloadResponse(path=path, content=content, error=None)

    async def _download_one(self, path: str, *, platform: str = "") -> FileDownloadResponse:
        """单文件下载：直接经 dispatch 取原始 dict，只解码 stdout 字段。

        不走 aexecute——它把 stdout+stderr 合并进 output，stderr 告警文本会
        混进 base64 流解码出损坏字节（executor 返回 dict 天然带独立 stdout 字段）。
        """
        result = await dispatch_local_call(
            self._user_id,
            "exec",
            {"command": self._download_command(path, platform=platform), "cwd": self.work_dir},
            timeout=float(self._exec_timeout),
        )
        return self._download_response(path, result)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        # 平台解析一次供整批命令使用（照 execute 的 asyncio.run 桥接约束）
        platform = _run_coro_sync(self._resolve_platform())
        return [self._upload_one(path, content, platform=platform) for path, content in files]

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        # 覆盖协议默认（to_thread 同步版）：直接走 aexecute，避免事件循环桥接；
        # 平台解析一次供整批命令使用（一次注册表读，容错默认 posix）
        platform = await self._resolve_platform()
        responses: list[FileUploadResponse] = []
        for path, content in files:
            responses.append(await self._aupload_one(path, content, platform=platform))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        platform = _run_coro_sync(self._resolve_platform())
        responses: list[FileDownloadResponse] = []
        for path in paths:
            try:
                responses.append(_run_coro_sync(self._download_one(path, platform=platform)))
            except AppError:
                raise
            except Exception:
                logger.exception("local download_files(%s) failed", path)
                responses.append(
                    file_download_response(path=path, content=None, error="file_not_found")
                )
        return responses

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        # 覆盖协议默认（to_thread 同步版）：直接走 dispatch，避免事件循环桥接；
        # 平台解析一次供整批命令使用（一次注册表读，容错默认 posix）
        platform = await self._resolve_platform()
        responses: list[FileDownloadResponse] = []
        for path in paths:
            try:
                responses.append(await self._download_one(path, platform=platform))
            except AppError:
                raise
            except Exception:
                logger.exception("local adownload_files(%s) failed", path)
                responses.append(
                    file_download_response(path=path, content=None, error="file_not_found")
                )
        return responses


def _restore_file_info_path(info: FileInfo, workspace_path: str) -> FileInfo:
    """把 ls/glob 返回的相对路径补回虚拟别名前缀；绝对路径原样保留。

    daemon 侧文件命令以相对路径（相对已映射 cwd）执行，返回值里的相对路径
    因此指向工作区内；补回 `/workspace/{sid}/` 前缀让模型看到的仍是别名
    视角的绝对路径。别名之外的绝对路径（如 /etc/hosts）是 daemon 机器的
    真实路径，没有别名含义，原样返回。
    """
    path = str(info.get("path", ""))
    if path.startswith("/"):
        return info
    restored: dict[str, object] = dict(info)
    restored["path"] = posixpath.normpath(f"{workspace_path}/{path}")
    return cast(FileInfo, restored)


class WorkspaceAliasBackend(LocalSandboxBackend):
    """虚拟别名路径剥离器：`/workspace/{sid}/x` → 相对路径 `x`（F1 修复）。

    prompt_policy 以 `work_dir = /workspace/{session_id}` 指示模型「文件工具
    一律用 {work_dir}/<name>」，但 daemon 只映射 cwd 不映射命令内路径——
    `/workspace/s1/note.txt` 会被 base64 进 python 脚本在 daemon 机器上解析，
    该绝对路径不存在 → file_not_found。本类在**命令构造之前**的方法入口做
    路径翻译（相对路径经已映射 cwd 落在正确目录），返回值中的相对路径再
    补回别名前缀（仿 WorkflowScopedBackend._strip_path 的模式）。别名之外
    的绝对路径（如 /etc/hostname）不改写，保持既有语义。
    """

    def _strip_path(self, path: str | None) -> str | None:
        if path is None or not self._session_id:
            return path
        work_dir = self.work_dir
        if path == work_dir or path == f"{work_dir}/":
            return "."
        prefix = f"{work_dir}/"
        if path.startswith(prefix):
            return path[len(prefix) :] or "."
        return path

    def _strip_required(self, path: str) -> str:
        """必填路径版剥离：`_strip_path` 对 str 入参不会产出 None，类型兜底原样返回。"""
        stripped = self._strip_path(path)
        return path if stripped is None else stripped

    def _restore_path(self, path: str) -> str:
        """相对路径 → 别名绝对路径（`./a` 与 `a` 归一为 `/workspace/{sid}/a`）。"""
        if path.startswith("/"):
            return path
        return posixpath.normpath(f"{self.work_dir}/{path}")

    def _strip_command(self, command: str) -> str:
        """shell 命令串里的别名 → `.`（`cd /workspace/s1` → `cd .`）。

        负向断言保证 `/workspace/s1` 之后必须是非路径字符（`/`、空白、串尾
        等），`/workspace/s12` 这类更长 sid 不被误改写。
        """
        if not self._session_id:
            return command
        return re.sub(re.escape(self.work_dir) + r"(?![A-Za-z0-9_.-])", ".", command)

    # ---- 命令执行：命令串内的别名改写 ----

    async def aexecute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        return await super().aexecute(self._strip_command(command), timeout=timeout)

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        return super().execute(self._strip_command(command), timeout=timeout)

    # ---- 读：路径参数剥离（结果无路径字段，无需回填） ----

    def read(self, file_path: str, offset: int = 0, limit: int = 2000):
        return super().read(self._strip_required(file_path), offset, limit)

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000):
        return await super().aread(self._strip_required(file_path), offset, limit)

    # ---- 列目录：剥离 + 条目路径回填 ----

    def ls(self, path: str) -> LsResult:
        result = super().ls(self._strip_required(path))
        if result.error or not result.entries:
            return result
        return LsResult(
            entries=[_restore_file_info_path(info, self.work_dir) for info in result.entries]
        )

    async def als(self, path: str) -> LsResult:
        result = await super().als(self._strip_required(path))
        if result.error or not result.entries:
            return result
        return LsResult(
            entries=[_restore_file_info_path(info, self.work_dir) for info in result.entries]
        )

    # ---- glob：绕开 _glob_search_root 的绝对化（相对根 "." 即已映射 cwd） ----

    def _glob_root(self, path: str | None) -> str:
        if path is None:
            return "/"  # 与 BaseSandbox.glob 的 None 语义一致：根搜索
        return self._strip_required(path)

    def _restore_glob(self, result: GlobResult) -> GlobResult:
        if result.error or not result.matches:
            return result
        return GlobResult(
            matches=[_restore_file_info_path(info, self.work_dir) for info in result.matches],
            truncated=result.truncated,
            truncation_reason=result.truncation_reason,
        )

    def glob(self, pattern: str, path: str | None = None) -> GlobResult:
        search_path = self._glob_root(path)
        result = super().execute(_build_glob_cmd(pattern, search_path))
        return self._restore_glob(_parse_glob_output(result, search_path))

    async def aglob(self, pattern: str, path: str | None = None) -> GlobResult:
        search_path = self._glob_root(path)
        try:
            result = await asyncio.wait_for(
                super().aexecute(_build_glob_cmd(pattern, search_path)),
                timeout=ASYNC_GLOB_TIMEOUT,
            )
        except TimeoutError:
            return GlobResult(
                error=(
                    f"Error: glob timed out after {ASYNC_GLOB_TIMEOUT}s. "
                    "Try a more specific pattern or a narrower path."
                )
            )
        return self._restore_glob(_parse_glob_output(result, search_path))

    # ---- grep：剥离搜索根 + 匹配路径回填 ----

    def _restore_grep(self, result: GrepResult) -> GrepResult:
        if result.error or not result.matches:
            return result
        return GrepResult(
            matches=[
                {**match, "path": self._restore_path(str(match["path"]))}
                for match in result.matches
            ],
            truncated=result.truncated,
        )

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        result = super().grep(pattern, self._strip_path(path), glob, max_count=max_count)
        return self._restore_grep(result)

    async def agrep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        result = await super().agrep(pattern, self._strip_path(path), glob, max_count=max_count)
        return self._restore_grep(result)

    # ---- 写/编辑/删除：剥离入参 + 结果路径回填 ----

    def write(self, file_path: str, content: str) -> WriteResult:
        result = super().write(self._strip_required(file_path), content)
        if result.path is not None and result.error is None:
            return WriteResult(error=None, path=file_path)
        return result

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        result = await super().awrite(self._strip_required(file_path), content)
        if result.path is not None and result.error is None:
            return WriteResult(error=None, path=file_path)
        return result

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False):
        result = super().edit(self._strip_required(file_path), old_string, new_string, replace_all)
        if result.path is not None:
            return EditResult(error=result.error, path=file_path, occurrences=result.occurrences)
        return result

    async def aedit(
        self, file_path: str, old_string: str, new_string: str, replace_all: bool = False
    ):
        result = await super().aedit(
            self._strip_required(file_path), old_string, new_string, replace_all
        )
        if result.path is not None:
            return EditResult(error=result.error, path=file_path, occurrences=result.occurrences)
        return result

    def delete(self, file_path: str) -> DeleteResult:
        result = super().delete(self._strip_required(file_path))
        if result.path is not None:
            return DeleteResult(path=file_path)
        return result

    async def adelete(self, file_path: str) -> DeleteResult:
        result = await super().adelete(self._strip_required(file_path))
        if result.path is not None:
            return DeleteResult(path=file_path)
        return result

    # ---- upload/download：入参剥离 + 响应路径回填 ----

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        stripped = [(self._strip_path(path) or path, content) for path, content in files]
        return [
            FileUploadResponse(path=path, error=result.error)
            for (path, _), result in zip(files, super().upload_files(stripped), strict=True)
        ]

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        stripped = [(self._strip_path(path) or path, content) for path, content in files]
        return [
            FileUploadResponse(path=path, error=result.error)
            for (path, _), result in zip(files, await super().aupload_files(stripped), strict=True)
        ]

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        stripped = [self._strip_path(path) or path for path in paths]
        return [
            FileDownloadResponse(path=path, content=result.content, error=result.error)
            for path, result in zip(paths, super().download_files(stripped), strict=True)
        ]

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        stripped = [self._strip_path(path) or path for path in paths]
        return [
            FileDownloadResponse(path=path, content=result.content, error=result.error)
            for path, result in zip(paths, await super().adownload_files(stripped), strict=True)
        ]
