"""fsops：win32 结构化文件操作的原生实现（M4 T3.5）。

deepagents BaseSandbox 的 read/ls/edit/grep 命令是多行 POSIX 脚本，cmd.exe
跑不了；daemon 收到 ``op=fs_*`` 后经 ``handle_fs_op`` 用原生 os/shutil/
fnmatch/re 执行。测试用真实 tmp_path 文件系统锁定：

- read 分页语义与 deepagents ``_READ_COMMAND_TEMPLATE`` 逐字段对齐
  （offset 行起/limit 行/total_lines/start_line/end_line/next_offset、
  空文件提示、no_lines_requested、二进制 base64、超限错误）；
- ls/glob/grep/edit/delete 的结果形状与错误码；
- 路径约束：一切 fs op 锁死在工作区内（绝对路径、``..``、symlink 出区
  一律拒绝——比 exec 的 shell 更紧）。
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from lambchat_sandbox import fsops
from lambchat_sandbox.executor import ExecutorError

# ---------- helpers ----------


def _payload(path: str | None = None, **kw) -> dict:
    """payload 骨架：路径类 op 位置传 path；glob/grep 显式传 ``pattern=``/``path=``。"""
    payload: dict = {"cwd": "/workspace/s1"}
    if path is not None:
        payload["path"] = path
    payload.update(kw)
    return payload


def _ws(tmp_path: Path) -> Path:
    """直接拿会话目录（data_root/s1）当工作区，测试里省一层间接。"""
    ws = tmp_path / "s1"
    ws.mkdir(exist_ok=True)
    return ws


def _op(op: str, payload: dict, tmp_path: Path) -> dict:
    return fsops.handle_fs_op(op, payload, tmp_path)


# ---------- fs_read：分页语义对齐 _READ_COMMAND_TEMPLATE ----------


def test_fs_read_first_page_returns_pagination_fields(tmp_path):
    (_ws(tmp_path) / "f.txt").write_text("l1\nl2\nl3\nl4\nl5\n", encoding="utf-8")
    data = _op("fs_read", _payload("f.txt", offset=0, limit=2), tmp_path)
    assert data == {
        "encoding": "utf-8",
        "content": "l1\nl2",
        "total_lines": 5,
        "start_line": 1,
        "end_line": 2,
        "next_offset": 2,
    }


def test_fs_read_tail_page_next_offset_null_at_eof(tmp_path):
    (_ws(tmp_path) / "f.txt").write_text("l1\nl2\nl3\nl4\nl5\n", encoding="utf-8")
    data = _op("fs_read", _payload("f.txt", offset=2, limit=10), tmp_path)
    assert data["content"] == "l3\nl4\nl5"
    assert data["start_line"] == 3
    assert data["end_line"] == 5
    assert data["total_lines"] == 5
    assert data["next_offset"] is None  # 读完即 null（模板同款）


def test_fs_read_offset_beyond_file_length_errors(tmp_path):
    (_ws(tmp_path) / "f.txt").write_text("only\n", encoding="utf-8")
    data = _op("fs_read", _payload("f.txt", offset=9, limit=5), tmp_path)
    assert data == {"error": "Line offset 9 exceeds file length (1 lines)"}


def test_fs_read_missing_limit_defaults_2000(tmp_path):
    (_ws(tmp_path) / "f.txt").write_text("a\n" * 2500, encoding="utf-8")
    data = _op("fs_read", _payload("f.txt", offset=0), tmp_path)
    assert data["total_lines"] == 2500
    assert data["end_line"] == 2000
    assert data["next_offset"] == 2000


def test_fs_read_negative_offset_clamped_to_zero(tmp_path):
    (_ws(tmp_path) / "f.txt").write_text("x\ny\n", encoding="utf-8")
    data = _op("fs_read", _payload("f.txt", offset=-5, limit=1), tmp_path)
    assert data["content"] == "x"
    assert data["start_line"] == 1


def test_fs_read_non_positive_limit_short_circuits_no_lines(tmp_path):
    (_ws(tmp_path) / "f.txt").write_text("x\n", encoding="utf-8")
    data = _op("fs_read", _payload("f.txt", offset=0, limit=0), tmp_path)
    assert data == {"encoding": "utf-8", "content": "", "no_lines_requested": True}


def test_fs_read_empty_file_returns_reminder(tmp_path):
    (_ws(tmp_path) / "empty.txt").write_text("", encoding="utf-8")
    data = _op("fs_read", _payload("empty.txt", offset=0, limit=10), tmp_path)
    assert data == {
        "encoding": "utf-8",
        "content": "System reminder: File exists but has empty contents",
    }


def test_fs_read_binary_file_base64_without_pagination(tmp_path):
    raw = b"\x00\x01payload\xff"
    (_ws(tmp_path) / "blob.bin").write_bytes(raw)
    data = _op("fs_read", _payload("blob.bin", offset=0, limit=5), tmp_path)
    assert data == {"encoding": "base64", "content": base64.b64encode(raw).decode("ascii")}


def test_fs_read_oversized_binary_errors_explicitly(tmp_path):
    # \x00 是合法 UTF-8（模板同判为文本）——必须用非法字节才走二进制分支
    (_ws(tmp_path) / "big.bin").write_bytes(b"\xff\xfe" + b"\x00" * fsops.MAX_BINARY_BYTES)
    data = _op("fs_read", _payload("big.bin"), tmp_path)
    assert data["error"].startswith("Binary file exceeds maximum preview size")


def test_fs_read_errors(tmp_path):
    _ws(tmp_path)
    assert _op("fs_read", _payload("missing.txt"), tmp_path) == {"error": "file_not_found"}
    (_ws(tmp_path) / "d").mkdir()
    assert _op("fs_read", _payload("d"), tmp_path) == {"error": "not_a_file"}


def test_fs_read_output_truncated_at_cap_with_marker(tmp_path):
    """文本页超 MAX_OUTPUT_BYTES 截断并附 TRUNCATION_MSG（模板同款）。"""
    ws = _ws(tmp_path)
    huge = "\n".join(f"line-{i}-{'x' * 100}" for i in range(20000)) + "\n"
    (ws / "big.txt").write_text(huge, encoding="utf-8")
    data = _op("fs_read", _payload("big.txt", offset=0, limit=20000), tmp_path)
    assert fsops.TRUNCATION_MSG in data["content"]
    assert len(data["content"].encode("utf-8")) <= fsops.MAX_OUTPUT_BYTES
    # 截断页仍可续读：next_offset 指向未读行
    assert data["next_offset"] is not None and data["next_offset"] > 0


# ---------- fs_ls ----------


def test_fs_ls_entries_use_virtual_relative_paths(tmp_path):
    ws = _ws(tmp_path)
    (ws / "note.txt").write_text("x", encoding="utf-8")
    (ws / "subdir").mkdir()
    data = _op("fs_ls", _payload("."), tmp_path)
    # os.path.join(".", name) 的 "./" 前缀与 ls 模板一致（服务端 normpath 消化）
    assert {"path": "./note.txt", "is_dir": False} in data["entries"]
    assert {"path": "./subdir", "is_dir": True} in data["entries"]


def test_fs_ls_subdirectory_joins_requested_path(tmp_path):
    ws = _ws(tmp_path)
    (ws / "sub").mkdir()
    (ws / "sub" / "a.txt").write_text("x", encoding="utf-8")
    data = _op("fs_ls", _payload("sub"), tmp_path)
    assert data["entries"] == [{"path": "sub/a.txt", "is_dir": False}]


def test_fs_ls_errors(tmp_path):
    _ws(tmp_path)
    assert _op("fs_ls", _payload("nope"), tmp_path) == {"error": "path_not_found"}
    (_ws(tmp_path) / "file.txt").write_text("x", encoding="utf-8")
    assert _op("fs_ls", _payload("file.txt"), tmp_path) == {"error": "not_a_directory"}


# ---------- fs_write ----------


def test_fs_write_decodes_b64_and_creates_parents(tmp_path):
    ws = _ws(tmp_path)
    content = "héllo\nbinary-safe ✓"
    data = _op(
        "fs_write",
        _payload("nested/dir/f.txt", content_b64=base64.b64encode(content.encode()).decode()),
        tmp_path,
    )
    assert data == {}
    assert (ws / "nested" / "dir" / "f.txt").read_text(encoding="utf-8") == content


def test_fs_write_roundtrips_through_fs_read(tmp_path):
    ws = _ws(tmp_path)
    body = "\n".join(f"line {i}" for i in range(10)) + "\n"
    _op(
        "fs_write",
        _payload("r.txt", content_b64=base64.b64encode(body.encode()).decode()),
        tmp_path,
    )
    data = _op("fs_read", _payload("r.txt", offset=0, limit=10), tmp_path)
    assert data["content"] == body.rstrip("\n")
    assert data["total_lines"] == 10


def test_fs_write_over_cap_rejected(tmp_path):
    _ws(tmp_path)
    big = b"x" * (fsops.FS_WRITE_MAX_BYTES + 1)
    data = _op(
        "fs_write",
        _payload("big.bin", content_b64=base64.b64encode(big).decode()),
        tmp_path,
    )
    assert data["error"].startswith("file_too_large")
    assert not (_ws(tmp_path) / "big.bin").exists()


def test_fs_write_invalid_base64_errors(tmp_path):
    _ws(tmp_path)
    data = _op("fs_write", _payload("f.txt", content_b64="not base64 !!"), tmp_path)
    assert "error" in data


# ---------- fs_edit（match-driven CRLF，对齐 _EDIT_COMMAND_TEMPLATE） ----------


def test_fs_edit_replaces_single_occurrence(tmp_path):
    ws = _ws(tmp_path)
    (ws / "f.txt").write_text("alpha beta gamma\n", encoding="utf-8")
    data = _op(
        "fs_edit",
        _payload(
            "f.txt",
            old_str_b64=base64.b64encode(b"beta").decode(),
            new_str_b64=base64.b64encode(b"BETA").decode(),
        ),
        tmp_path,
    )
    assert data == {"count": 1}
    assert (ws / "f.txt").read_text(encoding="utf-8") == "alpha BETA gamma\n"


def test_fs_edit_multiple_occurrences_requires_replace_all(tmp_path):
    ws = _ws(tmp_path)
    (ws / "f.txt").write_text("x x x\n", encoding="utf-8")
    data = _op(
        "fs_edit",
        _payload(
            "f.txt",
            old_str_b64=base64.b64encode(b"x").decode(),
            new_str_b64=base64.b64encode(b"y").decode(),
        ),
        tmp_path,
    )
    assert data["error"] == "multiple_occurrences"
    assert (ws / "f.txt").read_text(encoding="utf-8") == "x x x\n"  # 未改写


def test_fs_edit_replace_all(tmp_path):
    ws = _ws(tmp_path)
    (ws / "f.txt").write_text("x x x\n", encoding="utf-8")
    data = _op(
        "fs_edit",
        _payload(
            "f.txt",
            old_str_b64=base64.b64encode(b"x").decode(),
            new_str_b64=base64.b64encode(b"y").decode(),
            replace_all=True,
        ),
        tmp_path,
    )
    assert data == {"count": 3}
    assert (ws / "f.txt").read_text(encoding="utf-8") == "y y y\n"


def test_fs_edit_string_not_found(tmp_path):
    ws = _ws(tmp_path)
    (ws / "f.txt").write_text("content\n", encoding="utf-8")
    data = _op(
        "fs_edit",
        _payload(
            "f.txt",
            old_str_b64=base64.b64encode(b"zzz").decode(),
            new_str_b64=base64.b64encode(b"y").decode(),
        ),
        tmp_path,
    )
    assert data["error"] == "string_not_found"


def test_fs_edit_crlf_file_with_lf_old_string_preserves_style(tmp_path):
    """read 归一 CRLF 后 old_string 是 LF-only：匹配 CRLF 变体并保持文件风格。"""
    ws = _ws(tmp_path)
    (ws / "crlf.txt").write_bytes(b"a\r\nb\r\n")
    data = _op(
        "fs_edit",
        _payload(
            "crlf.txt",
            old_str_b64=base64.b64encode(b"a\nb").decode(),
            new_str_b64=base64.b64encode(b"x\ny").decode(),
        ),
        tmp_path,
    )
    assert data == {"count": 1}
    assert (ws / "crlf.txt").read_bytes() == b"x\r\ny\r\n"


def test_fs_edit_missing_file(tmp_path):
    _ws(tmp_path)
    data = _op(
        "fs_edit",
        _payload(
            "missing.txt",
            old_str_b64=base64.b64encode(b"a").decode(),
            new_str_b64=base64.b64encode(b"b").decode(),
        ),
        tmp_path,
    )
    assert data["error"] == "file_not_found"


# ---------- fs_delete ----------


def test_fs_delete_file(tmp_path):
    ws = _ws(tmp_path)
    (ws / "f.txt").write_text("x", encoding="utf-8")
    assert _op("fs_delete", _payload("f.txt"), tmp_path) == {}
    assert not (ws / "f.txt").exists()


def test_fs_delete_directory_recursive(tmp_path):
    ws = _ws(tmp_path)
    (ws / "tree" / "inner").mkdir(parents=True)
    (ws / "tree" / "inner" / "f.txt").write_text("x", encoding="utf-8")
    assert _op("fs_delete", _payload("tree"), tmp_path) == {}
    assert not (ws / "tree").exists()


def test_fs_delete_missing_errors(tmp_path):
    _ws(tmp_path)
    assert _op("fs_delete", _payload("ghost"), tmp_path) == {"error": "file_not_found"}


# ---------- fs_glob ----------


def test_fs_glob_basename_pattern_matches_any_depth(tmp_path):
    ws = _ws(tmp_path)
    (ws / "top.py").write_text("x", encoding="utf-8")
    (ws / "deep" / "nested").mkdir(parents=True)
    (ws / "deep" / "nested" / "inner.py").write_text("x", encoding="utf-8")
    (ws / "deep" / "nested" / "skip.txt").write_text("x", encoding="utf-8")
    data = _op("fs_glob", _payload(path="/", pattern="*.py"), tmp_path)
    paths = [m["path"] for m in data["matches"]]
    assert paths == ["deep/nested/inner.py", "top.py"]  # 排序 + 仅常规文件
    assert all(m["is_dir"] is False for m in data["matches"])


def test_fs_glob_path_relative_double_star(tmp_path):
    ws = _ws(tmp_path)
    (ws / "src" / "pkg").mkdir(parents=True)
    (ws / "src" / "pkg" / "m.py").write_text("x", encoding="utf-8")
    (ws / "src" / "top.py").write_text("x", encoding="utf-8")
    data = _op("fs_glob", _payload(path="/", pattern="src/**/*.py"), tmp_path)
    assert [m["path"] for m in data["matches"]] == ["src/pkg/m.py", "src/top.py"]


def test_fs_glob_hidden_basenames_excluded_unless_explicit(tmp_path):
    """os.walk 含隐藏目录（bare pattern 能命中其下普通名文件），但隐藏
    basename 本身要显式点模式才匹配（fnmatchcase 无 DOTMATCH，模板同款）。"""
    ws = _ws(tmp_path)
    (ws / ".hidden").mkdir()
    (ws / ".hidden" / "h.py").write_text("x", encoding="utf-8")
    (ws / ".profile").write_text("x", encoding="utf-8")
    (ws / "vis.py").write_text("x", encoding="utf-8")
    data = _op("fs_glob", _payload(path="/", pattern="*.py"), tmp_path)
    assert [m["path"] for m in data["matches"]] == [".hidden/h.py", "vis.py"]
    star = _op("fs_glob", _payload(path="/", pattern="*"), tmp_path)
    # "*" 匹配一切非隐藏 basename（.profile 排除、h.py 命中）
    assert [m["path"] for m in star["matches"]] == [".hidden/h.py", "vis.py"]
    explicit = _op("fs_glob", _payload(path="/", pattern=".hidden/*.py"), tmp_path)
    assert [m["path"] for m in explicit["matches"]] == [".hidden/h.py"]


def test_fs_glob_rooted_subpath(tmp_path):
    ws = _ws(tmp_path)
    (ws / "sub").mkdir()
    (ws / "sub" / "a.txt").write_text("x", encoding="utf-8")
    (ws / "b.txt").write_text("x", encoding="utf-8")
    data = _op("fs_glob", _payload(path="sub", pattern="*.txt"), tmp_path)
    assert [m["path"] for m in data["matches"]] == ["a.txt"]  # 相对搜索根


def test_fs_glob_missing_root_errors_path_not_found(tmp_path):
    """模板 prologue 的 chdir ENOENT → path_not_found（错误而非空集）。"""
    _ws(tmp_path)
    data = _op("fs_glob", _payload(path="ghost", pattern="*.py"), tmp_path)
    assert data == {"error": "path_not_found"}


def test_fs_glob_root_is_file_errors_not_a_directory(tmp_path):
    ws = _ws(tmp_path)
    (ws / "f.txt").write_text("x", encoding="utf-8")
    assert _op("fs_glob", _payload(path="f.txt", pattern="*"), tmp_path) == {
        "error": "not_a_directory"
    }


def test_fs_glob_traversal_pattern_rejected(tmp_path):
    _ws(tmp_path)
    assert _op("fs_glob", _payload(path="/", pattern="../*.py"), tmp_path) == {
        "error": "invalid_pattern"
    }


def test_fs_glob_match_cap_flags_truncated(tmp_path):
    ws = _ws(tmp_path)
    for i in range(5):
        (ws / "src").mkdir(exist_ok=True)
        (ws / "src" / f"m{i}.py").write_text("x", encoding="utf-8")
    original = fsops.MAX_MATCHES
    try:
        fsops.MAX_MATCHES = 2
        data = _op("fs_glob", _payload(path="/", pattern="src/*.py"), tmp_path)
    finally:
        fsops.MAX_MATCHES = original
    assert len(data["matches"]) == 2
    assert data["truncated"] is True
    assert data["truncation_reason"] == "budget"


# ---------- fs_grep ----------


def test_fs_grep_literal_matches_with_line_fields(tmp_path):
    ws = _ws(tmp_path)
    (ws / "a.txt").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    (ws / "sub").mkdir()
    (ws / "sub" / "b.txt").write_text("beta here\n", encoding="utf-8")
    data = _op("fs_grep", _payload(path=".", pattern="beta"), tmp_path)
    assert data == {
        "matches": [
            {"path": "./a.txt", "line": 2, "text": "beta"},
            {"path": "./sub/b.txt", "line": 1, "text": "beta here"},
        ],
        "truncated": False,
    }


def test_fs_grep_single_file_root_searches_file_directly(tmp_path):
    ws = _ws(tmp_path)
    (ws / "one.txt").write_text("hit\nmiss\nhit\n", encoding="utf-8")
    data = _op("fs_grep", _payload(path="one.txt", pattern="hit"), tmp_path)
    assert data["matches"] == [
        {"path": "one.txt", "line": 1, "text": "hit"},
        {"path": "one.txt", "line": 3, "text": "hit"},
    ]


def test_fs_grep_max_count_truncates(tmp_path):
    ws = _ws(tmp_path)
    (ws / "a.txt").write_text("x\n" * 10, encoding="utf-8")
    data = _op("fs_grep", _payload(path=".", pattern="x", max_count=3), tmp_path)
    assert len(data["matches"]) == 3
    assert data["truncated"] is True


def test_fs_grep_max_count_exact_cap_not_truncated(tmp_path):
    ws = _ws(tmp_path)
    (ws / "a.txt").write_text("x\n" * 3, encoding="utf-8")
    data = _op("fs_grep", _payload(path=".", pattern="x", max_count=3), tmp_path)
    assert len(data["matches"]) == 3
    assert data["truncated"] is False


def test_fs_grep_is_regex_mode(tmp_path):
    ws = _ws(tmp_path)
    (ws / "a.txt").write_text("foo123bar\nplain\n", encoding="utf-8")
    data = _op("fs_grep", _payload(path=".", pattern=r"\d+", is_regex=True), tmp_path)
    assert data["matches"] == [{"path": "./a.txt", "line": 1, "text": "foo123bar"}]


def test_fs_grep_literal_by_default_dots_not_regex(tmp_path):
    ws = _ws(tmp_path)
    (ws / "a.txt").write_text("a.b\naxb\n", encoding="utf-8")
    data = _op("fs_grep", _payload(path=".", pattern="a.b"), tmp_path)
    assert [m["line"] for m in data["matches"]] == [1]


def test_fs_grep_glob_filter_basenames(tmp_path):
    ws = _ws(tmp_path)
    (ws / "keep.py").write_text("hit\n", encoding="utf-8")
    (ws / "drop.txt").write_text("hit\n", encoding="utf-8")
    data = _op("fs_grep", _payload(path=".", pattern="hit", glob="*.py"), tmp_path)
    assert [m["path"] for m in data["matches"]] == ["./keep.py"]


def test_fs_grep_missing_root_returns_empty(tmp_path):
    _ws(tmp_path)
    data = _op("fs_grep", _payload(path="ghost", pattern="x"), tmp_path)
    assert data == {"matches": [], "truncated": False}


def test_fs_grep_invalid_regex_errors(tmp_path):
    _ws(tmp_path)
    data = _op("fs_grep", _payload(path=".", pattern="(unclosed", is_regex=True), tmp_path)
    assert "error" in data


# ---------- fs_upload：分块无状态写（truncate 首块 + offset 定位追加） ----------


def test_fs_upload_first_chunk_creates_file_with_parents(tmp_path):
    data = _op(
        "fs_upload",
        _payload(
            "sub/dir/f.bin",
            content_b64=base64.b64encode(b"hello").decode(),
            offset=0,
            truncate=True,
        ),
        tmp_path,
    )
    assert data == {"written": 5}
    assert (_ws(tmp_path) / "sub/dir/f.bin").read_bytes() == b"hello"


def test_fs_upload_later_chunk_writes_at_offset_without_truncate(tmp_path):
    ws = _ws(tmp_path)
    _op(
        "fs_upload",
        _payload("f.bin", content_b64=base64.b64encode(b"AAAA").decode(), offset=0, truncate=True),
        tmp_path,
    )
    data = _op(
        "fs_upload",
        _payload("f.bin", content_b64=base64.b64encode(b"BBBB").decode(), offset=4, truncate=False),
        tmp_path,
    )
    assert data == {"written": 4}
    assert (ws / "f.bin").read_bytes() == b"AAAABBBB"


def test_fs_upload_truncate_chunk_discards_previous_content(tmp_path):
    ws = _ws(tmp_path)
    (ws / "f.txt").write_bytes(b"old-and-long-content")
    _op(
        "fs_upload",
        _payload("f.txt", content_b64=base64.b64encode(b"new").decode(), offset=0, truncate=True),
        tmp_path,
    )
    assert (ws / "f.txt").read_bytes() == b"new"


def test_fs_upload_overlapping_offset_overwrites_in_place(tmp_path):
    ws = _ws(tmp_path)
    (ws / "f.bin").write_bytes(b"0123456789")
    _op(
        "fs_upload",
        _payload("f.bin", content_b64=base64.b64encode(b"XY").decode(), offset=3, truncate=False),
        tmp_path,
    )
    assert (ws / "f.bin").read_bytes() == b"012XY56789"


def test_fs_upload_binary_content_roundtrip(tmp_path):
    ws = _ws(tmp_path)
    raw = bytes(range(256)) * 8
    _op(
        "fs_upload",
        _payload("blob.bin", content_b64=base64.b64encode(raw).decode(), offset=0, truncate=True),
        tmp_path,
    )
    assert (ws / "blob.bin").read_bytes() == raw


def test_fs_upload_later_chunk_missing_file_errors(tmp_path):
    _ws(tmp_path)
    data = _op(
        "fs_upload",
        _payload("f.bin", content_b64=base64.b64encode(b"x").decode(), offset=0, truncate=False),
        tmp_path,
    )
    assert data == {"error": "file_not_found"}


def test_fs_upload_oversize_chunk_rejected(tmp_path):
    ws = _ws(tmp_path)
    raw = b"x" * (fsops.FS_TRANSFER_MAX_BYTES + 1)
    data = _op(
        "fs_upload",
        _payload("big.bin", content_b64=base64.b64encode(raw).decode(), offset=0, truncate=True),
        tmp_path,
    )
    assert "file_too_large" in data["error"]
    assert not (ws / "big.bin").exists()


def test_fs_upload_negative_offset_rejected(tmp_path):
    _ws(tmp_path)
    data = _op(
        "fs_upload",
        _payload("f.bin", content_b64=base64.b64encode(b"x").decode(), offset=-1, truncate=True),
        tmp_path,
    )
    assert "offset" in data["error"]


def test_fs_upload_rejects_path_escape(tmp_path):
    _ws(tmp_path)
    data = _op(
        "fs_upload",
        _payload(
            "../outside.bin", content_b64=base64.b64encode(b"x").decode(), offset=0, truncate=True
        ),
        tmp_path,
    )
    assert "escape" in data["error"]


# ---------- fs_download：分片无状态读（size + eof 终止协议） ----------


def test_fs_download_slice_returns_content_size_eof(tmp_path):
    ws = _ws(tmp_path)
    (ws / "f.bin").write_bytes(b"0123456789")
    data = _op("fs_download", _payload("f.bin", offset=2, length=4), tmp_path)
    assert base64.b64decode(data["content_b64"]) == b"2345"
    assert data["size"] == 10
    assert data["eof"] is False


def test_fs_download_short_final_slice_sets_eof(tmp_path):
    ws = _ws(tmp_path)
    (ws / "f.bin").write_bytes(b"0123456789")
    data = _op("fs_download", _payload("f.bin", offset=6, length=100), tmp_path)
    assert base64.b64decode(data["content_b64"]) == b"6789"
    assert data["size"] == 10
    assert data["eof"] is True


def test_fs_download_empty_file_returns_eof_immediately(tmp_path):
    ws = _ws(tmp_path)
    (ws / "empty.bin").write_bytes(b"")
    data = _op("fs_download", _payload("empty.bin", offset=0, length=64), tmp_path)
    assert base64.b64decode(data["content_b64"]) == b""
    assert data == {"content_b64": "", "size": 0, "eof": True}


def test_fs_download_exact_boundary_slice_sets_eof(tmp_path):
    ws = _ws(tmp_path)
    (ws / "f.bin").write_bytes(b"0123456789")
    data = _op("fs_download", _payload("f.bin", offset=0, length=10), tmp_path)
    assert data["eof"] is True
    data = _op("fs_download", _payload("f.bin", offset=0, length=9), tmp_path)
    assert data["eof"] is False


def test_fs_download_missing_file_and_directory_errors(tmp_path):
    ws = _ws(tmp_path)
    assert _op("fs_download", _payload("missing.bin", offset=0, length=1), tmp_path) == {
        "error": "file_not_found"
    }
    (ws / "adir").mkdir()
    assert _op("fs_download", _payload("adir", offset=0, length=1), tmp_path) == {
        "error": "is_directory"
    }


def test_fs_download_oversize_length_rejected(tmp_path):
    ws = _ws(tmp_path)
    (ws / "f.bin").write_bytes(b"0123456789")
    data = _op(
        "fs_download", _payload("f.bin", offset=0, length=fsops.FS_TRANSFER_MAX_BYTES + 1), tmp_path
    )
    assert "file_too_large" in data["error"]


def test_fs_download_offset_beyond_size_errors(tmp_path):
    ws = _ws(tmp_path)
    (ws / "f.bin").write_bytes(b"0123456789")
    data = _op("fs_download", _payload("f.bin", offset=11, length=1), tmp_path)
    assert "offset" in data["error"]


def test_fs_download_binary_content_roundtrip(tmp_path):
    ws = _ws(tmp_path)
    raw = bytes(range(256)) * 8
    (ws / "blob.bin").write_bytes(raw)
    data = _op(
        "fs_download", _payload("blob.bin", offset=0, length=fsops.FS_TRANSFER_MAX_BYTES), tmp_path
    )
    assert base64.b64decode(data["content_b64"]) == raw
    assert data["eof"] is True


# ---------- 路径约束（逃逸拒绝） ----------


@pytest.mark.parametrize(
    "escape_path",
    ["../outside.txt", "sub/../../escape.txt", "/etc/passwd"],
)
def test_fs_ops_reject_path_escape(tmp_path, escape_path):
    _ws(tmp_path)
    (tmp_path / "outside.txt").write_text("secret", encoding="utf-8")
    data = _op("fs_read", _payload(escape_path), tmp_path)
    assert "error" in data and "escape" in data["error"]


def test_fs_ops_reject_symlink_escape(tmp_path):
    ws = _ws(tmp_path)
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    (ws / "link.txt").symlink_to(tmp_path / "secret.txt")
    data = _op("fs_read", _payload("link.txt"), tmp_path)
    assert "error" in data and "escape" in data["error"]


def test_fs_ops_workspace_created_on_first_call(tmp_path):
    """首个 fs op 前工作区可不存在（exec 路径每次 mkdir，fs 对齐）。"""
    data = fsops.handle_fs_op("fs_ls", {"path": ".", "cwd": "/workspace/fresh"}, tmp_path)
    assert data == {"entries": []}
    assert (tmp_path / "fresh").is_dir()


# ---------- 分发与常量 ----------


def test_handle_fs_op_unknown_op_raises():
    with pytest.raises(ValueError, match="unknown fs op"):
        fsops.handle_fs_op("fs_chmod", {"cwd": "/workspace/s1"}, Path("/tmp/x"))


def test_handle_fs_op_invalid_cwd_raises_executor_error(tmp_path):
    with pytest.raises(ExecutorError):
        fsops.handle_fs_op("fs_read", {"path": "f", "cwd": "/etc"}, tmp_path)


def test_fs_op_sets_constant_interlock_with_deepagents():
    """daemon 侧常量与服务端 deepagents 模板字面量互锁（防漂移）。"""
    from deepagents.backends import sandbox as da_sandbox

    assert fsops.MAX_OUTPUT_BYTES == da_sandbox.MAX_OUTPUT_BYTES
    assert fsops.MAX_BINARY_BYTES == da_sandbox.MAX_BINARY_BYTES
    assert fsops.TRUNCATION_MSG == da_sandbox.TRUNCATION_MSG


def test_fs_op_registry_covers_all_documented_ops():
    assert fsops.FS_OPS == {
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
    assert fsops.WRITE_OPS == {"fs_write", "fs_edit", "fs_delete", "fs_upload"}


# ---------- fs_download_stream：单请求流式下载（二进制帧生成器） ----------

from lambchat_sandbox.frames import (  # noqa: E402
    FRAME_DATA,
    FRAME_EOF,
    FRAME_ERROR,
    FRAME_META,
)


def _stream_frames(payload: dict, tmp_path: Path) -> list[tuple[int, bytes]]:
    return list(fsops.handle_fs_stream("fs_download_stream", payload, tmp_path))


def _data_of(frames: list[tuple[int, bytes]]) -> bytes:
    return b"".join(p for t, p in frames if t == FRAME_DATA)


def test_fs_download_stream_yields_meta_data_eof(tmp_path):
    """正常流：首帧 meta(size)，数据帧为裸字节（无 base64），末帧 eof。"""
    ws = tmp_path / "s1"
    ws.mkdir()
    body = bytes(range(256)) * (2 * 4096 + 7)  # ~8MiB+7B → 4MiB 帧 ×3
    (ws / "big.bin").write_bytes(body)

    frames = _stream_frames({"cwd": "/workspace/s1", "path": "big.bin"}, tmp_path)

    assert frames[0] == (FRAME_META, b'{"size": %d}' % len(body))
    assert frames[-1] == (FRAME_EOF, b"")
    assert _data_of(frames) == body


def test_fs_download_stream_single_frame_for_small_file(tmp_path):
    ws = tmp_path / "s1"
    ws.mkdir()
    (ws / "a.txt").write_bytes(b"hello")
    frames = _stream_frames({"cwd": "/workspace/s1", "path": "a.txt"}, tmp_path)
    assert frames == [
        (FRAME_META, b'{"size": 5}'),
        (FRAME_DATA, b"hello"),
        (FRAME_EOF, b""),
    ]


def test_fs_download_stream_file_errors_are_single_error_frames(tmp_path):
    """缺文件/目录/超限：单个错误帧即收（错误串在 JSON payload 里）。"""
    ws = tmp_path / "s1"
    ws.mkdir()
    (ws / "d").mkdir()
    (ws / "a").write_bytes(b"xy")

    def err_text(frames):
        t, p = frames[0]
        assert t == FRAME_ERROR and len(frames) == 1
        import json as _json

        return _json.loads(p)["error"]

    assert err_text(_stream_frames({"cwd": "/workspace/s1", "path": "missing"}, tmp_path)) == (
        "file_not_found"
    )
    assert err_text(_stream_frames({"cwd": "/workspace/s1", "path": "d"}, tmp_path)) == (
        "is_directory"
    )
    assert err_text(
        _stream_frames({"cwd": "/workspace/s1", "path": "a", "max_bytes": 1}, tmp_path)
    ).startswith("file_too_large: 2 bytes exceeds 1 limit")


def test_fs_download_stream_rejects_absolute_path_as_error_frame(tmp_path):
    """绝对路径在流式 op 同样按逃逸拒绝（所有平台语义一致）——生成器不炸通道。"""
    tmp_path.joinpath("s1").mkdir()
    frames = _stream_frames({"cwd": "/workspace/s1", "path": "/etc/passwd"}, tmp_path)
    assert len(frames) == 1 and frames[0][0] == FRAME_ERROR
    assert "escapes workspace" in frames[0][1].decode()


def test_fs_download_stream_respects_offset_and_length(tmp_path):
    ws = tmp_path / "s1"
    ws.mkdir()
    (ws / "f").write_bytes(b"0123456789")
    frames = _stream_frames(
        {"cwd": "/workspace/s1", "path": "f", "offset": 3, "length": 4}, tmp_path
    )
    assert _data_of(frames) == b"3456"
    assert frames[0] == (FRAME_META, b'{"size": 10}')
    assert frames[-1] == (FRAME_EOF, b"")


def test_handle_fs_stream_unknown_op_raises():
    with pytest.raises(ValueError, match="unknown stream op"):
        fsops.handle_fs_stream("fs_upload_stream", {}, Path("/tmp/x"))
