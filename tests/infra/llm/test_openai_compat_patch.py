from __future__ import annotations

import json

from src.infra.llm.openai_compat_patch import apply_openai_compatible_patches


def test_openai_compatible_patch_accepts_plain_string_chat_response() -> None:
    from langchain_openai import ChatOpenAI

    apply_openai_compatible_patches()
    model = ChatOpenAI(model="gpt-test", api_key="sk-test")

    result = model._create_chat_result("plain provider text")

    assert result.generations[0].message.content == "plain provider text"


def test_openai_compatible_patch_accepts_json_string_chat_response() -> None:
    from langchain_openai import ChatOpenAI

    apply_openai_compatible_patches()
    model = ChatOpenAI(model="gpt-test", api_key="sk-test")
    payload = json.dumps(
        {
            "id": "chatcmpl-test",
            "model": "gpt-test",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "json provider text"},
                    "finish_reason": "stop",
                }
            ],
        }
    )

    result = model._create_chat_result(payload)

    assert result.generations[0].message.content == "json provider text"
