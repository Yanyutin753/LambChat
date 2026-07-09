"""
Team Agent - 基于角色的团队路由 Agent

特点：
- 无沙箱（使用内存 backend）
- 支持团队配置，按角色分派子代理
- 无团队时回退到单代理模式

架构:
    START -> team_router_node -> END
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict

from langchain_core.runnables import RunnableConfig

from src.agents.core.base import (
    BaseGraphAgent,
    GraphBuilder,
    build_presenter_langsmith_metadata,
    register_agent,
)
from src.agents.team_agent.context import TeamAgentContext
from src.agents.team_agent.nodes import team_router_node
from src.agents.team_agent.state import TeamAgentState
from src.infra.backend.context import set_user_context
from src.infra.logging import get_logger
from src.infra.task.exceptions import TaskInterruptedError
from src.infra.writer.present import Presenter, PresenterConfig
from src.kernel.config import settings

logger = get_logger(__name__)


# ============================================================================
# TeamAgent 类
# ============================================================================


@register_agent("team")
class TeamAgent(BaseGraphAgent):
    """
    Team Agent - 团队路由，角色分派

    适用于：
    - 多角色协作场景
    - 任务分解与分派
    - 无团队时回退到单代理模式
    """

    _agent_id = "team"
    _agent_name = "Team Agent"
    _name_key = "agents.team.name"
    _description = "团队路由 Agent，按角色分派子代理，无团队时回退到单代理模式"
    _description_key = "agents.team.description"
    _version = "1.0.0"
    _sort_order = 3  # 排序权重，数值越小越靠前
    _supports_sandbox = True

    _options = {
        "enable_thinking": {
            "type": "string",
            "default": "off",
            "label": "Thinking",
            "label_key": "agentOptions.enableThinking.label",
            "description": "Control thinking intensity (supported models only)",
            "description_key": "agentOptions.enableThinking.description",
            "icon": "Brain",
            "options": [
                {"value": "off", "label_key": "agentOptions.enableThinking.options.off"},
                {"value": "low", "label_key": "agentOptions.enableThinking.options.low"},
                {"value": "medium", "label_key": "agentOptions.enableThinking.options.medium"},
                {"value": "high", "label_key": "agentOptions.enableThinking.options.high"},
                {"value": "max", "label_key": "agentOptions.enableThinking.options.max"},
            ],
        },
        "enable_code_interpreter": {
            "type": "boolean",
            "default": False,
            "label": "Code Interpreter",
            "label_key": "agentOptions.enableCodeInterpreter.label",
            "description": "Run lightweight JavaScript/TypeScript in an isolated interpreter",
            "description_key": "agentOptions.enableCodeInterpreter.description",
            "icon": "Settings",
        },
    }

    @property
    def state_class(self) -> type:
        return TeamAgentState

    def build_graph(self, builder: GraphBuilder) -> None:
        """
        构建 Graph

        当前结构: START -> team_router_node -> END
        """
        builder.add_node("agent", team_router_node)
        builder.set_entry_point("agent")
        builder.add_edge("agent", "END")

    async def initialize(self) -> None:
        """初始化 Agent"""
        if self._initialized:
            return

        # Keep the outer graph stateless for now: it only wraps one router node, while
        # conversation history is persisted by the inner deep agent checkpointer.
        # If this outer graph grows into a multi-node workflow that needs resume or
        # per-node recovery, add an outer checkpointer with an isolated namespace or
        # thread id so it cannot collide with the inner graph's message state.
        builder = GraphBuilder(self.state_class)
        self.build_graph(builder)
        self._graph = builder.compile(
            checkpointer=None,
            recursion_limit=settings.SESSION_MAX_RUNS_PER_SESSION,
        )

        self._initialized = True
        logger.info(f"{self.name} initialized (no sandbox, no checkpointer)")

    async def _stream(
        self,
        message: str,
        session_id: str,
        user_id: str | None = None,
        presenter=None,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行 graph
        """
        if not self._initialized:
            await self.initialize()

        set_user_context(user_id or "default", session_id)

        if presenter is None:
            presenter = Presenter(
                PresenterConfig(
                    session_id=session_id,
                    agent_id=self.agent_id,
                    agent_name=self.name,
                    user_id=user_id,
                    enable_storage=True,
                )
            )

        # 创建并初始化 TeamAgentContext
        disabled_tools = kwargs.get("disabled_tools")
        disabled_skills = kwargs.get("disabled_skills")
        enabled_skills = kwargs.get("enabled_skills")
        disabled_mcp_tools = kwargs.get("disabled_mcp_tools")
        team_id = kwargs.get("team_id")
        context_enabled_skills = None if team_id else enabled_skills
        context = TeamAgentContext(
            session_id=session_id,
            agent_id=self.agent_id,
            user_id=user_id,
            disabled_tools=disabled_tools,
            disabled_skills=disabled_skills,
            enabled_skills=context_enabled_skills,
            disabled_mcp_tools=disabled_mcp_tools,
            auto_mode=kwargs.get("auto_mode", False),
        )
        await context.setup()

        # 发送 metadata
        yield presenter.metadata()

        # 构建 config
        agent_options = kwargs.get("agent_options", {})
        logger.info(f"[TeamAgent] agent_options: {agent_options}")

        langsmith_context = {
            "agent_options": agent_options,
            "disabled_skills": disabled_skills,
            "enabled_skills": context_enabled_skills,
            "persona_system_prompt": kwargs.get("persona_system_prompt"),
            "disabled_mcp_tools": disabled_mcp_tools,
            "base_url": kwargs.get("base_url", ""),
            "team_id": team_id,
            "active_goal": kwargs.get("active_goal"),
            "recommendation_input": kwargs.get("recommendation_input"),
            "attachments": kwargs.get("attachments", []),
        }
        langsmith_metadata = await build_presenter_langsmith_metadata(
            presenter,
            langsmith_context,
        )

        config: RunnableConfig = {
            "configurable": {
                "thread_id": session_id,
                "presenter": presenter,
                "context": context,
                "agent_options": agent_options,
                "disabled_skills": disabled_skills,
                "enabled_skills": context_enabled_skills,
                "persona_system_prompt": kwargs.get("persona_system_prompt"),
                "disabled_mcp_tools": disabled_mcp_tools,
                "base_url": kwargs.get("base_url", ""),
                "team_id": team_id,
                "active_goal": kwargs.get("active_goal"),
                "auto_mode": kwargs.get("auto_mode", False),
                "recommendation_input": kwargs.get("recommendation_input"),
            },
            "metadata": langsmith_metadata,
            "recursion_limit": settings.SESSION_MAX_RUNS_PER_SESSION,
        }

        # 初始状态
        attachments = kwargs.get("attachments", [])
        initial_state = {
            "input": message,
            "session_id": session_id,
            "messages": [],
            "output": "",
            "attachments": attachments,
        }
        logger.info(
            f"[TeamAgent] initial_state attachments: {len(attachments) if attachments else 0} items"
        )

        try:
            graph_task = asyncio.ensure_future(self._graph.ainvoke(initial_state, config))
            self._stream_tasks[presenter.run_id] = graph_task

            await graph_task

        except asyncio.CancelledError:
            if not graph_task.done():
                graph_task.cancel()
                try:
                    await graph_task
                except (asyncio.CancelledError, TaskInterruptedError):
                    pass
            raise

        except TaskInterruptedError:
            if not graph_task.done():
                graph_task.cancel()
                try:
                    await graph_task
                except (asyncio.CancelledError, TaskInterruptedError):
                    pass
            raise

        except Exception as e:
            yield presenter.error(str(e), type(e).__name__)
            raise

        finally:
            # goal:end 必须在 done 之前发出，保证事件顺序正确
            # 放在 finally 中确保即使异常也能发出
            active_goal = kwargs.get("active_goal")
            goal_started_at = kwargs.get("goal_started_at")
            if active_goal is not None:
                yield {
                    "event": "goal:end",
                    "data": {
                        "goal": active_goal,
                        "started_at": goal_started_at,
                        "ended_at": datetime.now(timezone.utc).isoformat(),
                    },
                }
            self._stream_tasks.pop(presenter.run_id, None)
            await context.close()

        yield presenter.done()
