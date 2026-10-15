from types import SimpleNamespace

import pytest

from src.infra.writer.present import Presenter, PresenterConfig


class _FakeDualWriter:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def create_trace(self, **kwargs):
        self.calls.append(kwargs)
        return True


class _FakeUserStorage:
    def __init__(self, user):
        self._user = user

    async def get_by_id(self, user_id: str):
        return self._user


@pytest.mark.asyncio
async def test_ensure_trace_includes_user_id_and_username_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    presenter = Presenter(
        PresenterConfig(
            session_id="session-1",
            agent_id="search",
            agent_name="Search Agent",
            user_id="user-123",
            model="selected-model",
            model_id="model-1",
        )
    )
    writer = _FakeDualWriter()

    async def fake_get_dual_writer():
        return writer

    monkeypatch.setattr(presenter, "_get_dual_writer", fake_get_dual_writer)
    monkeypatch.setattr(
        "src.infra.user.storage.UserStorage",
        lambda: _FakeUserStorage(SimpleNamespace(username="alice")),
    )

    await presenter._ensure_trace()

    assert len(writer.calls) == 1
    assert writer.calls[0]["metadata"]["user_id"] == "user-123"
    assert writer.calls[0]["metadata"]["username"] == "alice"
    assert writer.calls[0]["metadata"]["model"] == "selected-model"
    assert writer.calls[0]["metadata"]["model_id"] == "model-1"


@pytest.mark.asyncio
async def test_ensure_trace_keeps_user_id_when_username_lookup_misses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    presenter = Presenter(
        PresenterConfig(
            session_id="session-1",
            agent_id="search",
            agent_name="Search Agent",
            user_id="user-456",
        )
    )
    writer = _FakeDualWriter()

    async def fake_get_dual_writer():
        return writer

    monkeypatch.setattr(presenter, "_get_dual_writer", fake_get_dual_writer)
    monkeypatch.setattr("src.infra.user.storage.UserStorage", lambda: _FakeUserStorage(None))

    await presenter._ensure_trace()

    assert len(writer.calls) == 1
    assert writer.calls[0]["metadata"]["user_id"] == "user-456"
    assert "username" not in writer.calls[0]["metadata"]


def test_present_tool_start_compacts_large_input_and_tool_call_state() -> None:
    large_input = "x" * 20_000
    presenter = Presenter()

    event = presenter.present_tool_start(
        "large_tool",
        {"query": large_input},
        tool_call_id="tool-1",
    )

    assert event["data"]["args"]["query"] != large_input
    assert len(event["data"]["args"]["query"]) < 3_000
    assert "truncated from 20000 chars" in event["data"]["args"]["query"]
    assert len(presenter._tool_calls) == 1
    assert large_input not in str(presenter._tool_calls[0])


@pytest.mark.asyncio
async def test_langsmith_metadata_includes_runtime_context_and_bounded_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    presenter = Presenter(
        PresenterConfig(
            session_id="session-1",
            agent_id="team",
            agent_name="Team Agent",
            user_id="user-789",
            run_id="run-1",
            trace_id="trace-1",
        )
    )
    monkeypatch.setattr(
        "src.infra.user.storage.UserStorage",
        lambda: _FakeUserStorage(SimpleNamespace(username="charlie")),
    )

    metadata = await presenter.build_langsmith_metadata(
        {
            "team_id": "team-123",
            "agent_options": {
                "model": "openai/gpt-4.1",
                "model_id": "model-config-1",
                "temperature": 0.2,
                "top_p": 0.9,
                "max_tokens": 2048,
                "api_key": "secret",
                "_resolved_model_config": {"api_key": "also-secret"},
            },
            "enabled_skills": ["writer", "reviewer"],
            "disabled_skills": ["legacy"],
            "disabled_tools": ["shell"],
            "disabled_mcp_tools": ["dangerous_tool"],
            "persona_system_prompt": "Plan carefully." * 200,
            "attachments": [
                {"name": "brief.pdf", "type": "application/pdf", "size": 1234, "key": "file-key"},
                {"filename": "image.png", "mime_type": "image/png"},
            ],
            "active_goal": {"objective": "Ship the feature", "rubric": "Done means tests pass"},
            "recommendation_input": "What next?",
            "team_members": [
                {
                    "member_id": "member-1",
                    "role_name": "Designer",
                    "agent_id": "fast",
                    "model_id": "model-a",
                    "enabled": True,
                }
            ],
        }
    )

    assert metadata["agent_id"] == "team"
    assert metadata["agent_name"] == "Team Agent"
    assert metadata["session_id"] == "session-1"
    assert metadata["trace_id"] == "trace-1"
    assert metadata["run_id"] == "run-1"
    assert metadata["user_id"] == "user-789"
    assert metadata["username"] == "charlie"
    assert metadata["team_id"] == "team-123"
    assert metadata["model"] == "openai/gpt-4.1"
    assert metadata["model_id"] == "model-config-1"
    assert metadata["model_parameters"] == {
        "temperature": 0.2,
        "top_p": 0.9,
        "max_tokens": 2048,
    }
    assert metadata["skills"] == {"enabled": ["writer", "reviewer"], "disabled": ["legacy"]}
    assert metadata["tools"]["disabled"] == ["shell"]
    assert metadata["mcp_tools"]["disabled"] == ["dangerous_tool"]
    assert metadata["persona"]["enabled"] is True
    assert metadata["persona"]["prompt_length"] > metadata["persona"]["prompt_preview_chars"]
    assert metadata["attachments"]["count"] == 2
    assert metadata["attachments"]["items"][0] == {
        "name": "brief.pdf",
        "type": "application/pdf",
        "size": 1234,
        "has_key": True,
    }
    assert metadata["active_goal"]["objective"] == "Ship the feature"
    assert metadata["recommendation_input"]["preview"] == "What next?"
    assert metadata["team_members"][0]["role_name"] == "Designer"
    assert "api_key" not in str(metadata)
