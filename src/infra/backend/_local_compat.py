"""本地沙箱后端的纯函数层（自 local.py 拆出，守住后端文件 1000 行上限）。

Windows cmd.exe 参数引用 / 文件命令生成的平台分支上下文 / daemon 错误文本
分类 / ls·glob 相对路径回填 / 同步桥接——全部无副作用，不触网络与 redis。
monkeypatch 点（dispatch_local_call、_lookup_* 等）仍在 local.py：类代码经
local.py 命名空间解析这些名字，测试打桩路径不变；本模块的名字经 local.py
重导出（`local_module.X` 访问照旧）。
"""

from __future__ import annotations

import posixpath
import shlex
from dataclasses import dataclass
from typing import Any, Coroutine, TypeVar, cast

from src.infra.async_utils import loop_bridge
from src.infra.backend.protocol_compat import ExtendedFileError, FileInfo

T = TypeVar("T")

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


def _run_coro_sync(coro: Coroutine[Any, Any, T]) -> T:
    """在同步上下文中运行异步协程：经 loop_bridge 投递到进程主循环。

    直接 ``asyncio.run`` 会为每次调用新建临时事件循环，而协程内部使用的
    ``redis.asyncio`` 共享连接池绑定首个使用它的循环——跨循环复用报
    ``got Future attached to a different loop`` 并污染池（2026-09-06 生产
    事故：/api/sandbox/* 连锁 500、daemon 通道反复断连）。lifespan 已登记
    主循环，统一投递执行；未登记（脚本/测试）时 loop_bridge 内部退回
    ``asyncio.run``。活动循环内同步调用仍报错，要求改用异步 API。
    """
    return loop_bridge.run_coro_sync(coro)


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
