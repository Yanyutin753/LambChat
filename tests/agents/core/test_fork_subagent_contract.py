"""deepagents fork 模式契约测试：守护 context-worker 依赖的 SDK 行为。

LambChat 的 context-worker 子代理以 ``mode="fork"`` 接入（deepagents 0.7.12+），
依赖两个契约：fork 子代理收到父代理的完整对话历史；非法 mode 在构建期被拒绝。
deepagents 在 0.7 线内升级时若此测试变红，说明 fork 契约变化，需要重新适配。
"""

from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class _ScriptedChatModel(BaseChatModel):
    """按脚本顺序出消息、末条之后恒返末条的假模型，并记录每次输入消息。"""

    script: list[BaseMessage]
    i: int = 0
    calls: list[list[BaseMessage]] = []

    @property
    def _llm_type(self) -> str:
        return "scripted-fake"

    def bind_tools(self, tools: Any, **kwargs: Any) -> BaseChatModel:  # noqa: ARG002
        # 脚本已内嵌 tool call，绑定是空操作
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append(list(messages))
        message = self.script[min(self.i, len(self.script) - 1)]
        self.i += 1
        return ChatResult(generations=[ChatGeneration(message=message)])


async def test_fork_subagent_inherits_parent_conversation() -> None:
    from deepagents import create_deep_agent

    model = _ScriptedChatModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": {
                            "description": "Report the decision token established above.",
                            "subagent_type": "context-worker",
                        },
                        "id": "call_fork_1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="parent synthesis done"),
        ]
    )
    agent = create_deep_agent(
        model=model,
        system_prompt="You are the parent agent.",
        tools=[],
        subagents=[
            {
                "name": "context-worker",
                "description": "Continue work depending on the full parent conversation.",
                "system_prompt": "## Context Worker\nComplete the delegated task directly.",
                "mode": "fork",
            }
        ],
    )

    result = await agent.ainvoke(
        {"messages": [HumanMessage(content="Earlier we decided the token is FORK_TOKEN_7331.")]}
    )

    # 父代理收敛：拿到 task 工具结果并完成综合回复
    final_texts = [m.content for m in result["messages"] if isinstance(m, AIMessage)]
    assert any("parent synthesis done" in str(text) for text in final_texts)

    # fork 契约：某次模型调用的输入里同时包含父对话原文与 fork 任务前导，
    # 即子代理继承了父对话历史，而不是只收到孤立的委派描述
    fork_invocation = next(
        (
            messages
            for messages in model.calls
            if any("FORK_TOKEN_7331" in str(m.content) for m in messages)
            and any("prior conversation you are continuing" in str(m.content) for m in messages)
        ),
        None,
    )
    assert fork_invocation is not None, (
        "fork subagent did not receive the parent conversation history; "
        "deepagents fork contract changed?"
    )


async def test_invalid_subagent_mode_is_rejected_at_build() -> None:
    from deepagents.middleware.subagents import _build_task_tool

    try:
        _build_task_tool(
            [
                {
                    "name": "bad-mode-worker",
                    "description": "spec with an unsupported mode",
                    "mode": "unsupported-mode",
                }
            ]
        )
    except ValueError as exc:
        assert "invalid mode" in str(exc)
    else:
        raise AssertionError("unsupported subagent mode must raise ValueError at build time")
