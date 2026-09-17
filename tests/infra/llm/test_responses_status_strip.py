"""responses 线格式历史回传剥离只读输出字段。

上游 Responses API 的输出 item（reasoning / function_call 等）自带
``status`` 等只读字段，langchain 经 ``model_dump`` 原样存进消息历史；
下一轮全量重放时这些字段被带回 ``input`` 数组，严格校验的端点直接以
400 ``unknown_parameter`` 拒绝整个请求（生产 2026-09-17：
``input[13].status``，该会话每轮先 400 再 fallback，首字时间 ~7s）。
``status`` 是纯输出字段，任何合规端点都不接受它出现在 input item 顶层，
因此剥离应无条件执行。
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from src.infra.llm.client import LLMClient
from src.infra.llm.openai_chat import strip_readonly_responses_input_fields


def _responses_model():
    return LLMClient._create_model(
        "openai",
        "gpt-5.2",
        temperature=0.7,
        api_key="sk-test",
        api_format="responses",
    )


def _chat_model():
    return LLMClient._create_model(
        "openai",
        "gpt-5.2",
        temperature=0.7,
        api_key="sk-test",
    )


def _polluted_ai_message() -> AIMessage:
    """模拟生产污染：上游输出 item 被 model_dump 存进 content_blocks。"""
    return AIMessage(
        content="",
        content_blocks=[
            {
                "type": "reasoning",
                "id": "rs_1",
                "summary": [{"type": "summary_text", "text": "thought"}],
                "encrypted_content": "gAAAA-encrypted",
                "status": "completed",
            },
            {
                "type": "function_call",
                "name": "web_search",
                "arguments": '{"q": "x"}',
                "call_id": "call_1",
                "id": "fc_1",
                "status": "completed",
            },
        ],
    )


# ── 纯函数：payload 级剥离 ────────────────────────────────────────────────


def test_strip_removes_status_from_all_input_items() -> None:
    payload = {
        "input": [
            {"type": "message", "role": "user", "content": "hi"},
            {"type": "reasoning", "id": "rs_1", "status": "completed"},
            {"type": "function_call", "call_id": "c1", "status": "in_progress"},
        ]
    }
    result = strip_readonly_responses_input_fields(payload)
    assert all("status" not in item for item in result["input"])


def test_strip_preserves_other_item_fields() -> None:
    payload = {
        "input": [
            {
                "type": "reasoning",
                "id": "rs_1",
                "summary": [{"type": "summary_text", "text": "t"}],
                "encrypted_content": "ENC",
                "status": "completed",
            }
        ]
    }
    item = strip_readonly_responses_input_fields(payload)["input"][0]
    assert item == {
        "type": "reasoning",
        "id": "rs_1",
        "summary": [{"type": "summary_text", "text": "t"}],
        "encrypted_content": "ENC",
    }


def test_strip_ignores_non_dict_and_missing_input() -> None:
    assert strip_readonly_responses_input_fields({}) == {}
    assert strip_readonly_responses_input_fields({"input": "not-a-list"}) == {"input": "not-a-list"}
    result = strip_readonly_responses_input_fields(
        {"input": ["plain text", {"type": "message", "role": "user"}]}
    )
    assert result["input"] == ["plain text", {"type": "message", "role": "user"}]


def test_strip_does_not_touch_messages_payload() -> None:
    payload = {"messages": [{"role": "assistant", "content": "hi"}]}
    assert strip_readonly_responses_input_fields(payload) == payload


# ── 集成：_get_request_payload 出口剥离（生产 400 复现路径） ───────────────


def test_payload_strips_status_from_replayed_reasoning_item() -> None:
    model = _responses_model()
    payload = model._get_request_payload([HumanMessage(content="hi"), _polluted_ai_message()])
    reasoning_items = [
        i for i in payload["input"] if isinstance(i, dict) and i.get("type") == "reasoning"
    ]
    assert reasoning_items, "encrypted_content reasoning item should be replayed"
    assert all("status" not in item for item in reasoning_items)


def test_payload_strips_status_from_replayed_function_call_item() -> None:
    model = _responses_model()
    payload = model._get_request_payload([HumanMessage(content="hi"), _polluted_ai_message()])
    call_items = [
        i for i in payload["input"] if isinstance(i, dict) and i.get("type") == "function_call"
    ]
    assert call_items, "function_call item should be replayed"
    assert all("status" not in item for item in call_items)
    assert call_items[0]["call_id"] == "call_1"


def test_chat_completions_payload_unaffected() -> None:
    model = _chat_model()
    payload = model._get_request_payload([HumanMessage(content="hi")])
    assert "input" not in payload
    assert payload["messages"][0]["content"] == "hi"
