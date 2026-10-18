from copy import deepcopy

import pytest
from langchain_core.messages import HumanMessage

from src.agents.quick_agent.prompt import SEARCH_HANDOFF_TOOL
from src.infra.llm.google_chat import LambChatGoogleChatModel
from src.infra.llm.openai_chat import LambChatOpenAIChatModel


@pytest.mark.parametrize("binding", ["tools", "functions"])
def test_google_binding_preserves_shared_schema_for_later_responses_calls(binding):
    tool = deepcopy(SEARCH_HANDOFF_TOOL)
    original = deepcopy(tool)
    google = LambChatGoogleChatModel(model="gemini-3.8-flash", api_key="test")
    kwargs = (
        google.bind_tools([tool]).kwargs
        if binding == "tools"
        else {"functions": [tool["function"]]}
    )
    google._prepare_request([HumanMessage(content="hi")], **kwargs)
    assert tool == original

    responses = LambChatOpenAIChatModel(
        model="deepseek-flash", api_key="test", use_responses_api=True
    )
    bound = responses.bind_tools([tool])
    payload = responses._get_request_payload([HumanMessage(content="hi")], **bound.kwargs)
    assert payload["tools"][0]["parameters"] == original["function"]["parameters"]
