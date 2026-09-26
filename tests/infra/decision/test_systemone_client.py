"""System One 决策客户端（client.py）契约测试。"""

from __future__ import annotations

import json

import httpx
import pytest

from src.infra.decision import client as systemone
from src.kernel.config import settings


def _configure(monkeypatch, *, base="http://von.local", key="", model="von-1.1.0"):
    monkeypatch.setattr(settings, "SYSTEMONE_API_BASE", base)
    monkeypatch.setattr(settings, "SYSTEMONE_API_KEY", key)
    monkeypatch.setattr(settings, "SYSTEMONE_MODEL", model)
    monkeypatch.setattr(settings, "SYSTEMONE_TIMEOUT_SECONDS", 2.0)


def _ok_transport(payload: dict):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler), captured


@pytest.mark.asyncio
async def test_judge_noul_unconfigured_short_circuits(monkeypatch):
    _configure(monkeypatch, base="")

    called = []

    def handler(request: httpx.Request) -> httpx.Response:
        called.append(request)
        return httpx.Response(200, json={})

    assert await systemone.judge_noul("state", "q?", transport=httpx.MockTransport(handler)) is None
    assert called == []


@pytest.mark.asyncio
async def test_judge_noul_returns_probability_and_builds_request(monkeypatch):
    _configure(monkeypatch, key="sk-test")
    transport, captured = _ok_transport(
        {"model": "von-1.1.0", "answers": {"q": {"type": "noul", "noul": 0.83}}}
    )

    value = await systemone.judge_noul(
        "用户询问皮蛋供应商",
        "值得记忆吗？",
        criteria={"true": "t", "false": "f"},
        transport=transport,
    )

    assert value == pytest.approx(0.83)
    request = captured["request"]
    assert request.url.path == "/v1/systemone"
    assert request.headers["Authorization"] == "Bearer sk-test"
    body = json.loads(request.content)
    assert body["model"] == "von-1.1.0"
    assert body["state"] == "用户询问皮蛋供应商"
    question = body["questions"]["q"]
    assert question["type"] == "noul"
    assert question["criteria"] == {"true": "t", "false": "f"}


@pytest.mark.asyncio
async def test_auth_header_absent_without_key(monkeypatch):
    _configure(monkeypatch, key="")
    transport, captured = _ok_transport({"answers": {"q": {"type": "noul", "noul": 0.1}}})

    await systemone.judge_noul("state", "q?", transport=transport)

    assert "Authorization" not in captured["request"].headers


@pytest.mark.asyncio
async def test_http_error_returns_none(monkeypatch):
    _configure(monkeypatch)
    transport = httpx.MockTransport(lambda request: httpx.Response(500, json={}))

    assert await systemone.judge_noul("state", "q?", transport=transport) is None


@pytest.mark.asyncio
async def test_malformed_answers_return_none(monkeypatch):
    _configure(monkeypatch)

    missing_answers = httpx.MockTransport(lambda request: httpx.Response(200, json={"model": "m"}))
    assert await systemone.judge_noul("state", "q?", transport=missing_answers) is None

    missing_noul = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"answers": {"q": {"type": "noul"}}})
    )
    assert await systemone.judge_noul("state", "q?", transport=missing_noul) is None


@pytest.mark.asyncio
async def test_noul_value_clamped_to_unit_interval(monkeypatch):
    _configure(monkeypatch)
    high = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"answers": {"q": {"type": "noul", "noul": 1.7}}})
    )
    assert await systemone.judge_noul("state", "q?", transport=high) == 1.0

    low = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"answers": {"q": {"type": "noul", "noul": -0.2}}})
    )
    assert await systemone.judge_noul("state", "q?", transport=low) == 0.0
