"""结构化文件操作：daemon 平台为 win32 时文件工具的原生实现（M4 T3.5）。

背景：deepagents BaseSandbox 内置的 read/ls/write/edit/delete/glob/grep
命令是多行 POSIX 脚本（``2>/dev/null``、管道、heredoc、``rm -rf``），cmd.exe
无法执行。服务端（WorkspaceAliasBackend）在 daemon 上报平台为 win32 时改发
结构化 fs op，daemon 经 :func:`handle_fs_op` 用原生 os/shutil/fnmatch/re
执行——不再生成 shell 命令。

语义对齐：各 op 的结果字段与错误码对齐 deepagents ``sandbox.py`` 的对应
模板——read 的行分页（offset 行起/limit 行，返回 content/total_lines/
start_line/end_line/next_offset，空文件提示、no_lines_requested、二进制
base64、500KiB 截断消息）、edit 的 match-driven CRLF 处理、grep 的
``path/line/text`` 匹配记录与 max_count 截断语义。常量
（MAX_OUTPUT_BYTES 等）与服务端 deepagents 包字面量互锁（tests/client/
test_fsops.py）。

路径约束：fs op 的 path 一律相对当前虚拟工作区（payload 的 cwd 经
executor.map_workspace 映射 ``data_root/{sid}``），绝对路径、``..`` 上溯、
symlink 指出工作区一律拒绝——比 exec 的 shell（命令可达整机）更紧。
工作区在首个 fs op 前不存在时自动创建（对齐 executor 每次执行的 mkdir）。

与 deepagents 模板的**有意差异**（记录于任务报告）：

- glob 不做 brace 展开（``{a,b}``）与 ``[^...]`` 类改写——走单候选
  fnmatch 匹配，复杂模式覆盖面略窄；
- 二进制 read 统一受 MAX_BINARY_BYTES 预检（模板的 is_binary 分支原本
  无上限，靠 executor 输出截断兜底会把 JSON 截坏，fs 直达路径必须自查）；
- glob 根 ``/`` 映射为工作区根（模板语义是真实文件系统根——fs op 不允许
  出工作区，这是收紧而非放宽）。
"""

from __future__ import annotations

import base64
import binascii
import codecs
import fnmatch
import os
import re
import shutil
import stat as stat_module
import time
from pathlib import Path
from typing import Any, Callable

from lambchat_sandbox.executor import map_workspace

FS_OPS = frozenset(
    {
        "fs_read",
        "fs_ls",
        "fs_write",
        "fs_edit",
        "fs_delete",
        "fs_glob",
        "fs_grep",
        "fs_upload",
        "fs_download",
    }
)
"""daemon 支持的全部结构化 fs op（daemon.py 据此分发）。"""

WRITE_OPS = frozenset({"fs_write", "fs_edit", "fs_delete", "fs_upload"})
"""变更类 fs op：daemon 侧过确认门（读类只读，不确认）。"""

# 与 deepagents sandbox.py 常量字面量保持同步（tests/client/test_fsops.py 互锁）。
MAX_OUTPUT_BYTES = 500 * 1024
MAX_BINARY_BYTES = 500 * 1024
MAX_LINE_COUNT_BYTES = 1024 * 1024
TRUNCATION_MSG = (
    "\n\n[Output was truncated due to size limits. "
    "This paginated read result exceeded the sandbox stdout limit. "
    "Continue reading with a larger offset or smaller limit to inspect the rest of the file.]"
)

# glob/grep 的走查上限（对齐 _GLOB_COMMAND_TEMPLATE 的同名字面量）。
MAX_MATCHES = 10000
TIME_BUDGET = 5.0

#: fs_write 单次载荷上限：与服务端 results 通道 2MB 同量级（服务端也预检，
#: 这里是防伪造服务端的第二道闸）。
FS_WRITE_MAX_BYTES = 2 * 1024 * 1024

#: fs_upload 单块 / fs_download 单片的字节上限：与 FS_WRITE_MAX_BYTES 同源
#: （中继通道量级）；更大文件由服务端按 offset 分块多 op 完成，单 op 不放大。
FS_TRANSFER_MAX_BYTES = 2 * 1024 * 1024

_DEFAULT_READ_LIMIT = 2000


class FsOpError(Exception):
    """fs op 的可恢复错误（路径逃逸、坏载荷）：映射为结果级 error dict。"""


# ---------------------------------------------------------------------------
# 路径解析：虚拟相对路径 → 工作区内真实路径（逃逸拒绝）
# ---------------------------------------------------------------------------


def _resolve(raw: object, workspace: Path) -> Path:
    """把 fs op 的相对 path 解析到工作区内；绝对路径/上溯/ symlink 出区拒绝。

    空路径与 ``.`` 等价（工作区根）。返回的 target 经 resolve() 归一
    （symlink 展开 + ``..`` 折叠），再做包含检查——TOCTOU 窗口与 executor
    的命令级约束同级，是 best-effort 而非安全边界。
    """
    rel = "" if raw is None else str(raw)
    if not rel or rel == ".":
        return workspace
    candidate = Path(rel)
    if candidate.is_absolute():
        raise FsOpError(f"path escapes workspace: {rel!r}")
    root = workspace.resolve()
    target = (workspace / candidate).resolve()
    if target != root and root not in target.parents:
        raise FsOpError(f"path escapes workspace: {rel!r}")
    return target


def _os_error_code(exc: OSError) -> str:
    """OSError → deepagents 模板同款错误码（ENOENT 家族归 file_not_found）。"""
    if isinstance(exc, PermissionError):
        return "permission_denied"
    if isinstance(exc, (FileNotFoundError, NotADirectoryError)):
        return "file_not_found"
    if isinstance(exc, IsADirectoryError):
        return "not_a_file"
    return f"os_error: {exc}"


def _decode_b64(value: object, field: str) -> bytes:
    if not isinstance(value, str):
        raise FsOpError(f"{field} must be a base64 string")
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise FsOpError(f"invalid base64 in {field}") from exc


def _decode_b64_text(value: object, field: str) -> str:
    return _decode_b64(value, field).decode("utf-8")


# ---------------------------------------------------------------------------
# fs_read：行分页语义对齐 _READ_COMMAND_TEMPLATE
# ---------------------------------------------------------------------------


def _fs_read(payload: dict, workspace: Path) -> dict:
    path = _resolve(payload.get("path"), workspace)
    offset = max(0, int(payload.get("offset") or 0))
    raw_limit = payload.get("limit")
    limit = _DEFAULT_READ_LIMIT if raw_limit is None else int(raw_limit)
    try:
        st = path.stat()
        if not stat_module.S_ISREG(st.st_mode):
            return {"error": "not_a_file"}
        if st.st_size == 0:
            return {
                "encoding": "utf-8",
                "content": "System reminder: File exists but has empty contents",
            }

        with open(path, "rb") as f:
            raw_prefix = f.read(8192)
        # 8192 字节前缀可能切断多字节 UTF-8 字符：增量解码器缓存尾部残片而非
        # 抛错，合法文本不会被误判为二进制（模板同款手法）
        is_binary = False
        try:
            codecs.getincrementaldecoder("utf-8")().decode(raw_prefix, final=False)
        except UnicodeDecodeError:
            is_binary = True
        if is_binary:
            if st.st_size > MAX_BINARY_BYTES:
                return {
                    "error": (
                        f"Binary file exceeds maximum preview size of {MAX_BINARY_BYTES} bytes"
                    )
                }
            with open(path, "rb") as f:
                raw = f.read()
            return {"encoding": "base64", "content": base64.b64encode(raw).decode("ascii")}

        if limit <= 0:
            return {"encoding": "utf-8", "content": "", "no_lines_requested": True}

        return _read_text_page(path, offset, limit, st.st_size)
    except FsOpError:
        raise
    except OSError as exc:
        return {"error": _os_error_code(exc)}


def _read_text_page(path: Path, offset: int, limit: int, size: int) -> dict:
    """模板的行分页主循环：字节上限截断、EOF 判定、total_lines 有界重扫。"""
    line_count = 0
    returned_lines = 0
    truncated = False
    parts: list[str] = []
    current_bytes = 0
    msg_bytes = len(TRUNCATION_MSG.encode("utf-8"))
    effective_limit = MAX_OUTPUT_BYTES - msg_bytes

    at_eof = False
    with open(path, "r", encoding="utf-8", newline=None) as f:
        while line_count < offset:
            raw_line = f.readline()
            if raw_line == "":
                at_eof = True
                break
            line_count += 1

        while not at_eof and returned_lines < limit and not truncated:
            raw_line = f.readline()
            if raw_line == "":
                at_eof = True
                break
            line_count += 1
            line = raw_line.rstrip("\n").rstrip("\r")
            piece = line if returned_lines == 0 else "\n" + line
            piece_bytes = len(piece.encode("utf-8"))
            if current_bytes + piece_bytes > effective_limit:
                truncated = True
                remaining_bytes = effective_limit - current_bytes
                if remaining_bytes > 0:
                    prefix = piece.encode("utf-8")[:remaining_bytes].decode(
                        "utf-8", errors="ignore"
                    )
                    if prefix:
                        parts.append(prefix)
                        current_bytes += len(prefix.encode("utf-8"))
                break
            parts.append(piece)
            current_bytes += piece_bytes
            returned_lines += 1

        # 页满恰好停在 EOF 时 readline 未必返回空串：按文件位置判定
        # （整行读完后解码器状态干净，tell() 即字节偏移）
        if not at_eof:
            at_eof = f.tell() == size

    if returned_lines == 0 and not truncated:
        return {"error": f"Line offset {offset} exceeds file length ({line_count} lines)"}

    if at_eof:
        total_lines: int | None = line_count
    elif size <= MAX_LINE_COUNT_BYTES:
        with open(path, "r", encoding="utf-8", errors="surrogateescape", newline=None) as f:
            total_lines = sum(1 for _ in f)
    else:
        total_lines = None

    text = "".join(parts)
    if truncated:
        text += TRUNCATION_MSG
        # 首行就超限时推进一行，保证续读有进展（模板同款）
        if returned_lines == 0:
            returned_lines = 1

    end_line = offset + returned_lines
    if total_lines is not None:
        next_offset: int | None = end_line if end_line < total_lines else None
    else:
        next_offset = end_line
    return {
        "encoding": "utf-8",
        "content": text,
        "total_lines": total_lines,
        "start_line": offset + 1,
        "end_line": end_line,
        "next_offset": next_offset,
    }


# ---------------------------------------------------------------------------
# fs_ls：os.scandir 结构化列目录（路径用虚拟相对串拼接）
# ---------------------------------------------------------------------------


def _fs_ls(payload: dict, workspace: Path) -> dict:
    import posixpath

    rel = payload.get("path")
    rel_str = "" if rel is None else str(rel)
    path = _resolve(rel_str or ".", workspace)
    try:
        entries = []
        with os.scandir(path) as it:
            for entry in it:
                entries.append(
                    {
                        "path": posixpath.join(rel_str or ".", entry.name),
                        "is_dir": entry.is_dir(follow_symlinks=False),
                    }
                )
        return {"entries": entries}
    except FsOpError:
        raise
    except FileNotFoundError:
        return {"error": "path_not_found"}  # ls 模板同款错误码（非 file_not_found）
    except NotADirectoryError:
        return {"error": "not_a_directory"}
    except PermissionError:
        return {"error": "permission_denied"}
    except OSError as exc:
        return {"error": _os_error_code(exc)}


# ---------------------------------------------------------------------------
# fs_write / fs_edit / fs_delete
# ---------------------------------------------------------------------------


def _fs_write(payload: dict, workspace: Path) -> dict:
    path = _resolve(payload.get("path"), workspace)
    content = _decode_b64(payload.get("content_b64"), "content_b64")
    if len(content) > FS_WRITE_MAX_BYTES:
        return {
            "error": (
                f"file_too_large: {len(content)} bytes exceeds "
                f"{FS_WRITE_MAX_BYTES} limit (write cap)"
            )
        }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(content)
        return {}
    except FsOpError:
        raise
    except OSError as exc:
        return {"error": _os_error_code(exc)}


def _fs_edit(payload: dict, workspace: Path) -> dict:
    path = _resolve(payload.get("path"), workspace)
    old = _decode_b64_text(payload.get("old_str_b64"), "old_str_b64")
    new = _decode_b64_text(payload.get("new_str_b64"), "new_str_b64")
    replace_all = bool(payload.get("replace_all", False))
    try:
        st = path.stat()
        if not stat_module.S_ISREG(st.st_mode):
            return {"error": "not_a_file"}
        with open(path, "rb") as f:
            raw = f.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return {"error": "not_a_text_file"}

        # match-driven CRLF（模板同款）：read 归一 CRLF 后 old_string 是 LF-only，
        # 依次试原样/CRLF/LF 变体，首个命中决定文件该区域的行尾风格，new 同步
        # 变换以保持风格
        old_crlf = old.replace("\r\n", "\n").replace("\n", "\r\n")
        old_lf = old.replace("\r\n", "\n")
        new_crlf = new.replace("\r\n", "\n").replace("\n", "\r\n")
        new_lf = new.replace("\r\n", "\n")
        count = 0
        matched_old, matched_new = old, new
        for cand_old, cand_new in ((old, new), (old_crlf, new_crlf), (old_lf, new_lf)):
            c = text.count(cand_old)
            if c >= 1:
                matched_old, matched_new, count = cand_old, cand_new, c
                break
        if count == 0:
            return {"error": "string_not_found"}
        if count > 1 and not replace_all:
            return {"error": "multiple_occurrences"}

        result_text = (
            text.replace(matched_old, matched_new)
            if replace_all
            else text.replace(matched_old, matched_new, 1)
        )
        with open(path, "wb") as f:
            f.write(result_text.encode("utf-8"))
        return {"count": count}
    except FsOpError:
        raise
    except OSError as exc:
        return {"error": _os_error_code(exc)}


def _fs_delete(payload: dict, workspace: Path) -> dict:
    path = _resolve(payload.get("path"), workspace)
    try:
        if not os.path.lexists(path):
            return {"error": "file_not_found"}
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)  # 目录递归删除（rm -rf 语义）
        else:
            path.unlink()
        return {}
    except FsOpError:
        raise
    except OSError as exc:
        return {"error": _os_error_code(exc)}


# ---------------------------------------------------------------------------
# fs_glob：os.walk + 共享 basename/path-relative 匹配契约
# ---------------------------------------------------------------------------


def _parts_match(rel_parts: list[str], pat_parts: list[str]) -> bool:
    """分段匹配（``**`` 支持零层；隐藏段不穿越）——照搬模板的 memoized 实现。"""
    cache: dict[tuple[int, int], bool] = {}

    def match_from(ri: int, pi: int) -> bool:
        key = (ri, pi)
        if key in cache:
            return cache[key]
        result = _compute(ri, pi)
        cache[key] = result
        return result

    def _compute(ri: int, pi: int) -> bool:
        while pi < len(pat_parts):
            if pat_parts[pi] == "**":
                while pi < len(pat_parts) and pat_parts[pi] == "**":
                    pi += 1
                if pi == len(pat_parts):
                    # 尾部 ** 至少要求一层后代；a.py/** 不匹配文件 a.py
                    return ri < len(rel_parts) and all(
                        not part.startswith(".") for part in rel_parts[ri:]
                    )
                while ri <= len(rel_parts):
                    if match_from(ri, pi):
                        return True
                    if ri == len(rel_parts):
                        break
                    if rel_parts[ri].startswith("."):
                        return False
                    ri += 1
                return False
            if ri >= len(rel_parts):
                return False
            name = rel_parts[ri]
            seg = pat_parts[pi]
            if name.startswith(".") and not seg.startswith("."):
                return False
            if not fnmatch.fnmatchcase(name, seg):
                return False
            ri += 1
            pi += 1
        return ri == len(rel_parts)

    return match_from(0, 0)


def _path_match(rel: str, pattern: str) -> bool:
    rel_parts = [] if rel in ("", ".") else [seg for seg in rel.split("/") if seg]
    relative_candidate = pattern.lstrip("/")
    segments = relative_candidate.split("/")
    pat_parts = [seg for seg in segments if seg]
    if len(segments) > 1 and segments[-1] == "" and (not pat_parts or pat_parts[-1] != "**"):
        return False  # 尾斜杠 = 仅目录，而这里只出常规文件
    return _parts_match(rel_parts, pat_parts)


def _include_match(rel: str, pattern: str) -> bool:
    """共享契约：无 ``/`` → 任意深度的 basename；有 ``/`` → 路径相对匹配。"""
    if "/" not in pattern:
        name = rel.rsplit("/", 1)[-1]
        if name.startswith(".") and not pattern.startswith("."):
            return False
        return fnmatch.fnmatchcase(name, pattern)
    return _path_match(rel, pattern)


def _fs_glob(payload: dict, workspace: Path) -> dict:
    pattern = str(payload.get("pattern") or "")
    if not pattern or any(seg == ".." for seg in pattern.replace("\\", "/").split("/")):
        return {"error": "invalid_pattern"}
    root_str = str(payload.get("path") or "/")
    root = workspace if root_str == "/" else _resolve(root_str, workspace)
    try:
        if not root.exists() and not root.is_symlink():
            return {"error": "path_not_found"}  # 模板 prologue 的 chdir ENOENT 同款
        if root.is_file():
            return {"error": "not_a_directory"}
    except OSError as exc:
        return {"error": _os_error_code(exc)}

    real_root = str(root.resolve())
    prefix = real_root.rstrip(os.sep) + os.sep
    deadline = time.monotonic() + TIME_BUDGET
    matches: list[str] = []
    truncated = False
    reason: str | None = None
    walk_errors = 0

    def _on_error(_err: OSError) -> None:
        nonlocal walk_errors
        walk_errors += 1

    for dirpath, dirnames, filenames in os.walk(root, onerror=_on_error):
        dirnames.sort()
        filenames.sort()
        if time.monotonic() > deadline:
            truncated, reason = True, "budget"
            break
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if not _include_match(rel, pattern):
                continue
            candidate = os.path.realpath(full)
            if candidate != real_root and not candidate.startswith(prefix):
                continue  # symlink 指出搜索根：跳过（模板同款）
            if not os.path.isfile(candidate):
                continue  # 仅常规文件（断链 symlink 剔除）
            matches.append(rel)
            if len(matches) >= MAX_MATCHES:
                truncated, reason = True, "budget"
                break
        if truncated:
            break
    if walk_errors:
        truncated = True
        reason = "unreadable"
    matches.sort()  # 模板收尾 sorted(matches)：输出顺序确定
    return {
        "matches": [{"path": m, "is_dir": False} for m in matches],
        "truncated": truncated,
        "truncation_reason": reason,
    }


# ---------------------------------------------------------------------------
# fs_grep：字面量（默认）/正则行匹配，glob 过滤走共享契约
# ---------------------------------------------------------------------------


def _fs_grep(payload: dict, workspace: Path) -> dict:
    import posixpath

    pattern = str(payload.get("pattern") or "")
    if not pattern:
        return {"error": "invalid_pattern"}
    is_regex = bool(payload.get("is_regex", False))
    match_line: Callable[[str], bool]
    if is_regex:
        try:
            rx = re.compile(pattern)
        except re.error as exc:
            return {"error": f"invalid_regex: {exc}"}
        match_line = lambda line: rx.search(line) is not None  # noqa: E731
    else:
        match_line = lambda line: pattern in line  # noqa: E731

    glob_filter = payload.get("glob")
    glob_filter_str = str(glob_filter) if glob_filter else None
    raw_max = payload.get("max_count")
    max_count = int(raw_max) if raw_max is not None else None
    cap = (max_count + 1) if max_count is not None else None  # 多收一条判截断

    root_str = str(payload.get("path") or ".")
    root = _resolve(root_str, workspace)
    matches: list[dict] = []
    truncated = False

    if root.is_file():
        targets: list[tuple[Path, str]] = [(root, root_str)]
    else:
        targets = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            filenames.sort()
            for name in filenames:
                full = Path(dirpath) / name
                rel = os.path.relpath(full, root).replace(os.sep, "/")
                if glob_filter_str and not _include_match(rel, glob_filter_str):
                    continue
                targets.append((full, posixpath.join(root_str, rel)))

    for filepath, display in targets:
        try:
            fh = open(filepath, "r", encoding="utf-8", errors="ignore")
        except OSError:
            continue
        with fh:
            for i, line in enumerate(fh, 1):
                if match_line(line):
                    matches.append({"path": display, "line": i, "text": line.rstrip("\n")})
                    if cap is not None and len(matches) >= cap:
                        truncated = True
                        break
        if truncated:
            break
    if max_count is not None:
        matches = matches[:max_count]
    return {"matches": matches, "truncated": truncated}


# ---------------------------------------------------------------------------
# fs_upload / fs_download：结构化传输 op（无状态分块协议）
#
# 取代 upload/download 走 exec 的 base64 命令往返（win32 cmd.exe 命令行
# 8191 字符上限使 >~6KB 的文件上传必败，且 shell 往返对二进制内容天然
# 脆弱）。协议按字节 offset 定位、每块独立幂等——无 daemon 会话状态，
# 重传/续传天然安全：
#
# - fs_upload：``{path, content_b64, offset, truncate}``；首块 truncate=True
#   建父目录并截断创建，后续块 r+b 定位写（文件须已存在）；
# - fs_download：``{path, offset, length}`` → ``{content_b64, size, eof}``；
#   服务端循环到 eof 终止，size 供上层做进度/一致性核对。
# ---------------------------------------------------------------------------


def _payload_int(payload: dict, field: str, *, default: int, minimum: int) -> int:
    """载荷整型字段净化：非整型/越界一律 FsOpError（结果级错误）。"""
    try:
        value = int(payload.get(field, default))
    except (TypeError, ValueError):
        raise FsOpError(f"{field} must be an integer") from None
    if value < minimum:
        raise FsOpError(f"{field} must be >= {minimum}")
    return value


def _fs_upload(payload: dict, workspace: Path) -> dict:
    path = _resolve(payload.get("path"), workspace)
    content = _decode_b64(payload.get("content_b64"), "content_b64")
    if len(content) > FS_TRANSFER_MAX_BYTES:
        return {
            "error": (
                f"file_too_large: {len(content)} bytes exceeds "
                f"{FS_TRANSFER_MAX_BYTES} limit (upload chunk cap)"
            )
        }
    offset = _payload_int(payload, "offset", default=0, minimum=0)
    truncate = bool(payload.get("truncate"))
    try:
        if truncate:
            path.parent.mkdir(parents=True, exist_ok=True)
            mode = "wb"
        else:
            mode = "r+b"
        with open(path, mode) as f:
            f.seek(offset)
            f.write(content)
        return {"written": len(content)}
    except FsOpError:
        raise
    except OSError as exc:
        return {"error": _os_error_code(exc)}


def _fs_download(payload: dict, workspace: Path) -> dict:
    path = _resolve(payload.get("path"), workspace)
    length = _payload_int(payload, "length", default=0, minimum=1)
    if length > FS_TRANSFER_MAX_BYTES:
        return {
            "error": (
                f"file_too_large: {length} bytes exceeds "
                f"{FS_TRANSFER_MAX_BYTES} limit (download slice cap)"
            )
        }
    offset = _payload_int(payload, "offset", default=0, minimum=0)
    try:
        st = path.stat()
    except OSError as exc:
        return {"error": _os_error_code(exc)}
    if stat_module.S_ISDIR(st.st_mode):
        return {"error": "is_directory"}
    if not stat_module.S_ISREG(st.st_mode):
        return {"error": "not_a_file"}
    if offset > st.st_size:
        return {"error": f"offset {offset} beyond end of file ({st.st_size} bytes)"}
    try:
        with open(path, "rb") as f:
            f.seek(offset)
            chunk = f.read(length)
    except OSError as exc:
        return {"error": _os_error_code(exc)}
    return {
        "content_b64": base64.b64encode(chunk).decode("ascii"),
        "size": st.st_size,
        "eof": offset + len(chunk) >= st.st_size,
    }


# ---------------------------------------------------------------------------
# 分发入口
# ---------------------------------------------------------------------------


_HANDLERS: dict[str, Callable[[dict, Path], dict]] = {
    "fs_read": _fs_read,
    "fs_ls": _fs_ls,
    "fs_write": _fs_write,
    "fs_edit": _fs_edit,
    "fs_delete": _fs_delete,
    "fs_glob": _fs_glob,
    "fs_grep": _fs_grep,
    "fs_upload": _fs_upload,
    "fs_download": _fs_download,
}


def handle_fs_op(op: str, payload: dict[str, Any], data_root: Path) -> dict:
    """执行一个结构化 fs op，返回结果 dict（文件级错误也在结果里，非异常）。

    - 未知 op 抛 ``ValueError``、非法 cwd 抛 :class:`ExecutorError`（daemon
      转为 ``status=error`` 的 done，与 exec 的对应路径对齐）；
    - :class:`FsOpError`（路径逃逸/坏载荷）是**结果级**错误——模型可改路径
      重试，不应炸通道；
    - 其余异常上抛，由 daemon 收敛为 ``status=error``。
    """
    handler = _HANDLERS.get(op)
    if handler is None:
        raise ValueError(f"unknown fs op: {op}")
    workspace = map_workspace(str(payload.get("cwd", "")), Path(data_root))
    workspace.mkdir(parents=True, exist_ok=True)  # 对齐 executor：工作区按需创建
    try:
        return handler(payload, workspace)
    except FsOpError as exc:
        return {"error": str(exc)}
