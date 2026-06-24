from __future__ import annotations

import pytest

from src.infra.client_sandbox.models import ClientSandboxRpcResponse


class FakeRouter:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def call(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["operation"] == "write_file":
            return ClientSandboxRpcResponse(
                request_id="rpc-1",
                ok=True,
                result={"message": "Wrote /tmp/workspace/story.md"},
            )
        if kwargs["operation"] == "read_file":
            return ClientSandboxRpcResponse(
                request_id="rpc-1",
                ok=True,
                result={"content": "hello\nworld\n"},
            )
        if kwargs["operation"] == "list":
            return ClientSandboxRpcResponse(
                request_id="rpc-1",
                ok=True,
                result={
                    "entries": [
                        {
                            "path": "/tmp/workspace/story.md",
                            "is_dir": False,
                            "size": 7,
                            "modified_at": "1",
                        }
                    ]
                },
            )
        return ClientSandboxRpcResponse(
            request_id="rpc-1",
            ok=True,
            result={"output": "hello\n", "exit_code": 0, "truncated": False},
        )


class FakeStorage:
    def __init__(self, binding) -> None:
        self.binding = binding

    async def get_active_binding(self, user_id: str, session_id: str):
        assert user_id == "user-1"
        assert session_id == "session-1"
        return self.binding


class FakeBinding:
    device_id = "device-1"
    workspace_root = "/tmp/workspace"


@pytest.mark.asyncio
async def test_client_sandbox_backend_aexecute_converts_rpc_result() -> None:
    from src.infra.backend.client_sandbox import ClientSandboxBackend

    router = FakeRouter()
    backend = ClientSandboxBackend(
        user_id="user-1",
        session_id="session-1",
        storage=FakeStorage(FakeBinding()),
        router=router,
    )

    result = await backend.aexecute("echo hello", timeout=5)

    assert result.output == "hello\n"
    assert result.exit_code == 0
    assert result.truncated is False
    assert router.calls[0]["operation"] == "execute"
    assert router.calls[0]["payload"]["command"] == "echo hello"
    assert router.calls[0]["payload"]["cwd"] == "/workspace"


@pytest.mark.asyncio
async def test_client_sandbox_backend_fails_without_active_binding() -> None:
    from src.infra.backend.client_sandbox import ClientSandboxBackend

    backend = ClientSandboxBackend(
        user_id="user-1",
        session_id="session-1",
        storage=FakeStorage(None),
        router=FakeRouter(),
    )

    result = await backend.aexecute("echo hello", timeout=5)

    assert result.exit_code == -1
    assert "No active desktop sandbox binding" in result.output


@pytest.mark.asyncio
async def test_client_sandbox_backend_awrite_returns_write_result() -> None:
    from src.infra.backend.client_sandbox import ClientSandboxBackend

    router = FakeRouter()
    backend = ClientSandboxBackend(
        user_id="user-1",
        session_id="session-1",
        storage=FakeStorage(FakeBinding()),
        router=router,
    )

    result = await backend.awrite("/tmp/workspace/story.md", "# Story")

    assert result.error is None
    assert result.path == "/tmp/workspace/story.md"
    assert result.files_update is None
    assert router.calls[0]["operation"] == "write_file"
    assert router.calls[0]["payload"] == {
        "path": "/tmp/workspace/story.md",
        "content": "# Story",
    }


@pytest.mark.asyncio
async def test_client_sandbox_backend_read_and_list_protocol_shapes() -> None:
    from src.infra.backend.client_sandbox import ClientSandboxBackend

    router = FakeRouter()
    backend = ClientSandboxBackend(
        user_id="user-1",
        session_id="session-1",
        storage=FakeStorage(FakeBinding()),
        router=router,
    )

    read_result = await backend.aread("/tmp/workspace/story.md")
    list_result = await backend.als_info("/tmp/workspace")

    assert "hello" in read_result
    assert list_result == [
        {
            "path": "/tmp/workspace/story.md",
            "is_dir": False,
            "size": 7,
            "modified_at": "1",
        }
    ]


@pytest.mark.asyncio
async def test_client_sandbox_backend_glob_grep_and_edit_protocol_shapes() -> None:
    from src.infra.backend.client_sandbox import ClientSandboxBackend

    class CommandRouter(FakeRouter):
        async def call(self, **kwargs):
            self.calls.append(kwargs)
            command = kwargs["payload"].get("command", "")
            if "glob.glob(" in command:
                return ClientSandboxRpcResponse(
                    request_id="rpc-1",
                    ok=True,
                    result={
                        "output": '{"path": "/tmp/workspace/story.md", "is_dir": false, "size": 7}\n',
                        "exit_code": 0,
                        "truncated": False,
                    },
                )
            if "grep -rHnF" in command:
                return ClientSandboxRpcResponse(
                    request_id="rpc-1",
                    ok=True,
                    result={
                        "output": "/tmp/workspace/story.md:1:needle\n",
                        "exit_code": 0,
                        "truncated": False,
                    },
                )
            if "path.write_text" in command:
                return ClientSandboxRpcResponse(
                    request_id="rpc-1",
                    ok=True,
                    result={"output": "1\n", "exit_code": 0, "truncated": False},
                )
            return await super().call(**kwargs)

    router = CommandRouter()
    backend = ClientSandboxBackend(
        user_id="user-1",
        session_id="session-1",
        storage=FakeStorage(FakeBinding()),
        router=router,
    )

    glob_result = await backend.aglob_info("*.md", "/tmp/workspace")
    grep_result = await backend.agrep_raw("needle", path="/tmp/workspace")
    edit_result = await backend.aedit("/tmp/workspace/story.md", "old", "new")

    assert glob_result == [{"path": "/tmp/workspace/story.md", "is_dir": False, "size": 7}]
    assert grep_result == [{"path": "/tmp/workspace/story.md", "line": 1, "text": "needle"}]
    assert edit_result.error is None
    assert edit_result.path == "/tmp/workspace/story.md"
    assert edit_result.occurrences == 1
