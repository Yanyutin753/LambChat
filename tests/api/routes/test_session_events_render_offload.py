"""全量历史响应的 JSON 序列化必须离开事件循环。

不传 limit 时事件全量返回（可达 20MB+）；FastAPI 对返回 dict 的
jsonable_encoder+json.dumps 默认跑在事件循环上，长会话单请求内联可达数百 ms。
gzip 侧 starlette GZipMiddleware（≥128KiB）已自带线程卸载，无需处理；
小响应保持返回 dict，走 FastAPI 常规路径。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import Response

from src.api.routes import session as session_routes
from src.kernel.schemas.user import TokenPayload


def _user() -> TokenPayload:
    return TokenPayload(sub="u1", username="tester", exp=9999999999)


def _event(index: int) -> dict[str, Any]:
    return {"event_type": "message", "data": {"content": f"body-{index}"}, "seq": index}


def _patch_route(monkeypatch: pytest.MonkeyPatch, events: list[dict[str, Any]]) -> None:
    async def _fake_get_session(self, session_id: str):
        del self, session_id
        return SimpleNamespace(user_id="u1", metadata=None)

    monkeypatch.setattr(session_routes.SessionManager, "get_session", _fake_get_session)

    class _FakeDualWriter:
        async def read_session_events(
            self,
            session_id: str,
            types_list: list[str] | None,
            *,
            run_id: str | None = None,
            exclude_run_id: str | None = None,
            completed_only: bool = True,
            max_events: int | None = None,
        ) -> list[dict[str, Any]]:
            del session_id, types_list, run_id, exclude_run_id, completed_only, max_events
            return list(events)

    import src.infra.session.dual_writer as dual_writer_module

    monkeypatch.setattr(dual_writer_module, "get_dual_writer", lambda: _FakeDualWriter())


async def _call(event_count: int):
    return await session_routes.get_session_events(
        "session-1",
        event_types=None,
        run_id=None,
        exclude_run_id=None,
        limit=None,
        include_active_user_message=False,
        trace_limit=None,
        before_trace_started_at=None,
        before_trace_id=None,
        compact_message_chunks=False,
        user=_user(),
    )


@pytest.mark.asyncio
async def test_large_history_json_rendering_is_offloaded(monkeypatch: pytest.MonkeyPatch) -> None:
    threshold = session_routes._HISTORY_JSON_OFFLOAD_EVENT_COUNT
    _patch_route(monkeypatch, [_event(i) for i in range(threshold + 1)])

    offloaded: list[Any] = []
    original = session_routes.run_long_blocking_io

    async def _spy(func, *args, **kwargs):
        offloaded.append(func)
        return await original(func, *args, **kwargs)

    monkeypatch.setattr(session_routes, "run_long_blocking_io", _spy)

    result = await _call(threshold + 1)

    assert session_routes._render_history_json_bytes in offloaded
    assert isinstance(result, Response)
    assert result.media_type == "application/json"
    import json as json_mod

    payload = json_mod.loads(result.body)
    assert len(payload["events"]) == threshold + 1
    assert payload["session_id"] == "session-1"


@pytest.mark.asyncio
async def test_small_history_response_stays_plain_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_route(monkeypatch, [_event(i) for i in range(3)])

    result = await _call(3)

    assert isinstance(result, dict)
    assert len(result["events"]) == 3
