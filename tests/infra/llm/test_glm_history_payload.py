from copy import deepcopy

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.infra.llm.client import LLMClient


@pytest.mark.parametrize("name", ["glm-4.7", "glm-5.3"])
@pytest.mark.parametrize("tool_turn", [False, True])
def test_glm_final_payload_preserves_reasoning_history(name, tool_turn):
    model = LLMClient._create_model("zhipu", name, api_key="test-only")
    assistant = AIMessage(
        content="" if tool_turn else "Answer",
        additional_kwargs={"reasoning_content": "Original thinking\n原始思考 "},
        response_metadata={"model_name": name},
        tool_calls=[{"name": "lookup", "args": {}, "id": "call_1"}] if tool_turn else [],
    )
    messages = [HumanMessage(content="Question"), assistant]
    messages.append(
        ToolMessage(content="Result", tool_call_id="call_1")
        if tool_turn
        else HumanMessage(content="Continue")
    )
    original = deepcopy(messages)

    payload = model._get_request_payload(messages)

    assert payload["messages"][1]["reasoning_content"] == "Original thinking\n原始思考 "
    assert messages == original
