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

from copy import deepcopy

import pytest
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


def test_strip_normalizes_non_array_summary_on_replayed_items() -> None:
    """生产 2026-11-17：input[3].summary expected an array（严格端点 400）。"""
    payload = {
        "input": [
            {"type": "message", "role": "user", "content": "hi"},
            {
                "type": "reasoning",
                "content": [{"type": "reasoning_text", "text": "thinking"}],
                "summary": "历史上游存下的字符串型 summary",
            },
            {
                "type": "reasoning",
                "content": [{"type": "reasoning_text", "text": "thinking2"}],
                "summary": {"bad": "shape"},
            },
            {
                "type": "reasoning",
                "content": [{"type": "reasoning_text", "text": "ok"}],
                "summary": [{"type": "summary_text", "text": "本来就是数组"}],
            },
        ]
    }

    result = strip_readonly_responses_input_fields(payload)

    summaries = [item.get("summary") for item in result["input"]]
    assert summaries[0] is None
    # 字符串 summary 归一化为 summary_text 数组
    assert summaries[1] == [{"type": "summary_text", "text": "历史上游存下的字符串型 summary"}]
    # 必填数组不能通过删除字段规避校验
    assert summaries[2] == []
    # 本来就合规的数组原样保留
    assert summaries[3] == [{"type": "summary_text", "text": "本来就是数组"}]


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({}, []),
        ({"summary": None}, []),
        ({"summary": 17}, []),
        (
            {"summary": {"type": "summary_text", "text": "saved"}},
            [{"type": "summary_text", "text": "saved"}],
        ),
    ],
)
def test_reasoning_summary_is_always_an_array(fields, expected):
    item = {"type": "reasoning", "id": "rs_1", "encrypted_content": "ENC", **fields}
    payload = strip_readonly_responses_input_fields({"input": [item]})
    assert payload["input"][0]["summary"] == expected
    assert payload["input"][0]["encrypted_content"] == "ENC"


@pytest.mark.parametrize(
    "summary", [None, "saved reasoning", {"type": "summary_text", "text": "saved"}]
)
def test_request_normalizes_replayed_summary_without_mutating_history(summary):
    message = _polluted_ai_message()
    message.content[0]["summary"] = summary
    before = deepcopy(message.model_dump())
    payload = _responses_model()._get_request_payload([HumanMessage(content="hi"), message])
    reasoning = next(item for item in payload["input"] if item.get("type") == "reasoning")
    assert isinstance(reasoning["summary"], list)
    assert reasoning["encrypted_content"] == "gAAAA-encrypted"
    assert message.model_dump() == before
