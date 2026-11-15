"""Replay file references without crashing Chat Completions serialization."""

import copy

import pytest
from langchain_core.messages import HumanMessage, ToolMessage

from src.infra.llm.azure_chat import LambChatAzureChatModel
from src.infra.llm.openai_chat import LambChatOpenAIChatModel


@pytest.mark.parametrize("role", ["human", "tool"])
@pytest.mark.parametrize(
    "block",
    [
        {"type": "file", "url": "https://files.example/report.pdf", "mime_type": "application/pdf"},
        {"type": "file", "source_type": "url", "url": "https://files.example/report.pdf"},
    ],
)
def test_chat_file_url_is_a_text_reference_without_mutating_history(role, block):
    model = LambChatOpenAIChatModel(model="test-chat", api_key="test", use_responses_api=False)
    content = [{"type": "text", "text": "Read the report"}, block]
    message = (
        HumanMessage(content=content)
        if role == "human"
        else ToolMessage(content=content, tool_call_id="call-1")
    )
    before = copy.deepcopy(message)

    payload = model._get_request_payload([message])

    assert message == before
    blocks = payload["messages"][0]["content"]
    assert blocks[0] == content[0]
    assert blocks[1]["type"] == "text"
    assert "https://files.example/report.pdf" in blocks[1]["text"]
    if role == "tool":
        assert payload["messages"][0]["tool_call_id"] == "call-1"


def test_responses_keeps_native_file_url():
    model = LambChatOpenAIChatModel(model="test-chat", api_key="test", use_responses_api=True)
    message = HumanMessage(
        content=[
            {
                "type": "file",
                "url": "https://files.example/report.pdf",
                "mime_type": "application/pdf",
            }
        ]
    )

    payload = model._get_request_payload([message])

    assert payload["input"][0]["content"][0] == {
        "type": "input_file",
        "file_url": "https://files.example/report.pdf",
    }


def test_chat_keeps_native_file_ids():
    model = LambChatOpenAIChatModel(model="test-chat", api_key="test", use_responses_api=False)
    message = HumanMessage(content=[{"type": "file", "file_id": "file-1"}])

    assert model._get_request_payload([message])["messages"][0]["content"] == [
        {"type": "file", "file": {"file_id": "file-1"}}
    ]


def test_azure_chat_also_replays_file_urls():
    model = LambChatAzureChatModel(
        azure_endpoint="https://test.openai.azure.com",
        azure_deployment="test",
        api_version="2024-10-21",
        api_key="test",
        use_responses_api=False,
    )
    message = HumanMessage(
        content=[
            {
                "type": "file",
                "url": "https://files.example/report.pdf",
                "mime_type": "application/pdf",
            }
        ]
    )

    block = model._get_request_payload([message])["messages"][0]["content"][0]

    assert block["type"] == "text"
    assert "https://files.example/report.pdf" in block["text"]
