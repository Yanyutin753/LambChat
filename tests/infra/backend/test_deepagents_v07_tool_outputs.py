from __future__ import annotations

from deepagents import FilesystemMiddleware
from deepagents.backends.protocol import GlobResult, LsResult, ReadResult
from deepagents.backends.utils import create_file_data, slice_read_response
from langchain.tools import ToolRuntime


class _ToolOutputBackend:
    def __init__(self, content: str = "") -> None:
        self.content = content

    def ls(self, _path: str) -> LsResult:
        return LsResult(entries=[])

    def glob(self, pattern: str, path: str | None = None) -> GlobResult:
        del pattern, path
        return GlobResult(matches=[])

    def read(self, _file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        return slice_read_response(create_file_data(self.content), offset, limit)


def _runtime() -> ToolRuntime:
    return ToolRuntime(
        state={},
        context=None,
        config={},
        stream_writer=lambda _chunk: None,
        tool_call_id="tool-call-1",
        store=None,
    )


def _tool(middleware: FilesystemMiddleware, name: str):
    return next(tool for tool in middleware.tools if tool.name == name)


def test_v07_empty_ls_and_glob_tools_return_no_files_found() -> None:
    middleware = FilesystemMiddleware(backend=_ToolOutputBackend())
    runtime = _runtime()

    listed = _tool(middleware, "ls").func(path="/", runtime=runtime)
    globbed = _tool(middleware, "glob").func(pattern="*.py", path="/", runtime=runtime)

    assert listed.content == "No files found"
    assert globbed.content == "No files found"


def test_v07_read_file_uses_dynamic_two_space_line_markers() -> None:
    content = "".join(f"line {line_number}\n" for line_number in range(1, 101))
    middleware = FilesystemMiddleware(backend=_ToolOutputBackend(content))

    result = _tool(middleware, "read_file").func(
        file_path="/report.txt",
        offset=98,
        limit=2,
        runtime=_runtime(),
    )

    assert result.content == " 99  line 99\n100  line 100"
    assert "\t" not in result.content
