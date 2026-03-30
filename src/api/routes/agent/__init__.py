"""
Agent 路由

提供 Agent 列表和流式聊天接口。
每个 Agent 就是一个 Graph，流式请求接入 graph 后输出 SSE 事件。
"""

import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from src.agents.core.base import AgentFactory
from src.api.deps import get_current_user_optional, get_current_user_required
from src.infra.logging import get_logger
from src.kernel.config import settings
from src.kernel.schemas.agent import (
    AgentRequest,
    ToolInfo,
    ToolParamInfo,
    ToolsListResponse,
)
from src.kernel.schemas.user import TokenPayload

router = APIRouter()
logger = get_logger(__name__)

# 内置工具定义（带参数）
BUILTIN_TOOLS = [
    ToolInfo(
        name="read_file",
        description="读取文件内容",
        category="sandbox",
        parameters=[
            ToolParamInfo(name="file_path", type="string", description="文件路径", required=True),
        ],
    ),
    ToolInfo(
        name="write_file",
        description="写入文件",
        category="sandbox",
        parameters=[
            ToolParamInfo(name="file_path", type="string", description="文件路径", required=True),
            ToolParamInfo(name="content", type="string", description="文件内容", required=True),
        ],
    ),
    ToolInfo(
        name="edit_file",
        description="编辑文件",
        category="sandbox",
        parameters=[
            ToolParamInfo(name="file_path", type="string", description="文件路径", required=True),
            ToolParamInfo(
                name="old_string",
                type="string",
                description="要替换的内容",
                required=True,
            ),
            ToolParamInfo(name="new_string", type="string", description="新内容", required=True),
        ],
    ),
    ToolInfo(
        name="ls",
        description="列出目录内容",
        category="sandbox",
        parameters=[
            ToolParamInfo(name="path", type="string", description="目录路径", required=False),
        ],
    ),
    ToolInfo(
        name="glob",
        description="按模式搜索文件",
        category="sandbox",
        parameters=[
            ToolParamInfo(name="pattern", type="string", description="glob 模式", required=True),
            ToolParamInfo(name="path", type="string", description="搜索路径", required=False),
        ],
    ),
    ToolInfo(
        name="grep",
        description="在文件中搜索内容",
        category="sandbox",
        parameters=[
            ToolParamInfo(
                name="pattern",
                type="string",
                description="正则表达式模式",
                required=True,
            ),
            ToolParamInfo(name="path", type="string", description="搜索路径", required=False),
        ],
    ),
    ToolInfo(
        name="bash",
        description="执行 shell 命令",
        category="sandbox",
        parameters=[
            ToolParamInfo(name="command", type="string", description="要执行的命令", required=True),
        ],
    ),
]

# Sandbox MCP 管理工具定义
SANDBOX_MCP_TOOLS = [
    ToolInfo(
        name="sandbox_mcp_add",
        description="在沙箱中注册新的 MCP 服务器，并持久化到数据库",
        category="sandbox",
        parameters=[
            ToolParamInfo(
                name="server_name", type="string", description="服务器名称", required=True
            ),
            ToolParamInfo(
                name="command",
                type="string",
                description="stdio 启动命令, 如 'npx @anthropic/mcp-server-fetch'",
                required=True,
            ),
            ToolParamInfo(
                name="env_keys",
                type="string",
                description="环境变量 KEY 名称，逗号分隔",
                required=False,
            ),
        ],
    ),
    ToolInfo(
        name="sandbox_mcp_update",
        description="更新沙箱中 MCP 服务器的命令或环境变量，并持久化到数据库",
        category="sandbox",
        parameters=[
            ToolParamInfo(
                name="server_name", type="string", description="服务器名称", required=True
            ),
            ToolParamInfo(
                name="command",
                type="string",
                description="新的 stdio 命令（省略则不变更）",
                required=False,
            ),
            ToolParamInfo(
                name="env_keys",
                type="string",
                description="环境变量 KEY 名称，逗号分隔（省略则不变更）",
                required=False,
            ),
        ],
    ),
    ToolInfo(
        name="sandbox_mcp_remove",
        description="从沙箱中移除 MCP 服务器，并从数据库删除",
        category="sandbox",
        parameters=[
            ToolParamInfo(
                name="server_name", type="string", description="服务器名称", required=True
            ),
        ],
    ),
]

# Human 工具定义
HUMAN_TOOLS = [
    ToolInfo(
        name="ask_human",
        description="请求人工输入",
        category="human",
        parameters=[
            ToolParamInfo(name="message", type="string", description="提示信息", required=True),
        ],
    ),
]


def extract_tool_parameters(tool) -> list[ToolParamInfo]:
    """从 LangChain 工具中提取参数信息"""
    parameters: list[ToolParamInfo] = []
    try:
        if hasattr(tool, "args_schema") and tool.args_schema:
            # MCP tools may have args_schema as a dict directly, while LangChain tools have Pydantic models
            if isinstance(tool.args_schema, dict):
                schema = tool.args_schema
            else:
                try:
                    schema = tool.args_schema.schema()
                except Exception as e:
                    # Pydantic may fail to generate schema for types like Callable
                    logger.warning(f"Failed to generate schema for tool {tool.name}: {e}")
                    return parameters
            properties = schema.get("properties", {})
            required = set(schema.get("required", []))

            for param_name, param_info in properties.items():
                param_type = "string"
                if isinstance(param_info, dict):
                    param_type = param_info.get("type", "string")
                    if param_type == "array":
                        param_type = "list"
                    elif param_type == "object":
                        param_type = "dict"
                    elif param_type == "integer" or param_type == "number":
                        param_type = "number"
                    elif param_type == "boolean":
                        param_type = "boolean"

                parameters.append(
                    ToolParamInfo(
                        name=param_name,
                        type=param_type,
                        description=(
                            param_info.get("description", "")
                            if isinstance(param_info, dict)
                            else ""
                        ),
                        required=param_name in required,
                        default=(
                            param_info.get("default") if isinstance(param_info, dict) else None
                        ),
                    )
                )
    except Exception as e:
        logger.warning(f"Failed to extract parameters for tool {tool.name}: {e}")

    return parameters


@router.get("/agents")
async def list_agents(
    optional_user: Optional[TokenPayload] = Depends(get_current_user_optional),
):
    """列出当前用户可用的 Agent（按名称排序，默认 agent 排在最前面）"""
    from src.infra.agent.config_storage import get_agent_config_storage
    from src.infra.user.storage import UserStorage

    # 如果用户未登录，返回空列表
    if not optional_user:
        return {
            "agents": [],
            "count": 0,
            "default_agent": settings.DEFAULT_AGENT,
        }

    # 从数据库获取最新用户信息（包括角色）
    user_storage = UserStorage()
    db_user = await user_storage.get_by_id(optional_user.sub)

    # 使用数据库中的角色
    user_roles = db_user.roles if db_user else optional_user.roles
    logger.info(
        f"[Agents API] user_id={optional_user.sub}, db_user={db_user}, user_roles_from_db={user_roles}, user_roles_from_token={optional_user.roles}"
    )

    storage = get_agent_config_storage()

    # 获取用户的默认 agent 设置
    user_preference = await storage.get_user_preference(optional_user.sub)
    default_agent = user_preference.default_agent_id if user_preference else settings.DEFAULT_AGENT

    # 获取用户角色的可用 agents 映射（使用角色ID作为key）
    role_agent_map = {}
    role_ids = []  # 用户角色ID列表
    if user_roles:
        from src.infra.role.manager import get_role_manager

        role_manager = get_role_manager()
        for role_name in user_roles:
            role = await role_manager.get_role_by_name(role_name)
            if role:
                role_ids.append(role.id)
                role_agents = await storage.get_role_agents(role.id)
                # None = 未配置, list = 已配置(空列表表示明确禁止所有)
                role_agent_map[role.id] = role_agents
                logger.info(
                    f"[Agents API] role_name={role_name}, role_id={role.id}, role_agents={role_agents}"
                )

    logger.info(f"[Agents API] final role_ids={role_ids}, role_agent_map={role_agent_map}")

    # 获取过滤后的 agents
    agents = await AgentFactory.get_filtered_agents(
        user_roles=role_ids,  # 传入角色ID列表
        role_agent_map=role_agent_map,
        default_agent_id=default_agent,
    )

    return {
        "agents": agents,
        "count": len(agents),
        "default_agent": default_agent,
    }


@router.post("/{agent_id}/chat")
async def chat(
    agent_id: str,
    request: AgentRequest,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    非流式聊天接口

    调用 Agent.invoke() 并返回最终结果。
    """
    agent = await AgentFactory.get(agent_id)
    response = await agent.invoke(
        request.message,
        request.session_id or str(uuid.uuid4()),
    )
    return {"response": response}


@router.post("/{agent_id}/stream")
async def chat_stream(
    agent_id: str,
    request_body: AgentRequest,
    request: Request,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    流式聊天接口

    调用 Agent.stream()，每个 Agent 就是一个 CompiledGraph。
    流式请求接入 graph，节点通过 config 获取 Presenter 输出 SSE 事件。
    需要认证，session 会绑定到当前用户。
    """
    agent = await AgentFactory.get(agent_id)
    session_id = request_body.session_id or str(uuid.uuid4())
    user_id = user.sub  # 在闭包外部捕获

    # 获取 base_url（用于生成完整的文件 URL）
    # 优先 APP_BASE_URL 环境变量，fallback 到 request.base_url
    base_url = getattr(settings, "APP_BASE_URL", "").rstrip("/")
    if not base_url:
        base_url = str(request.base_url).rstrip("/")
        if base_url == "http://None":
            base_url = ""

    # Pass all agent_options to the agent
    agent_options = request_body.agent_options or {}
    logger.info(f"[API] request.agent_options: {request_body.agent_options}")
    logger.info(f"[API] agent_options to pass: {agent_options}")
    logger.info(f"[API] disabled_tools: {request_body.disabled_tools}")

    async def event_generator():
        try:
            async for event in agent.stream(
                request_body.message,
                session_id,
                user_id=user_id,
                disabled_tools=request_body.disabled_tools,
                agent_options=agent_options,
                base_url=base_url,
            ):
                # event 格式: {"event": "xxx", "data": {...}}
                # 确保 data 被正确序列化为 JSON
                data_str = (
                    event["data"]
                    if isinstance(event["data"], str)
                    else json.dumps(event["data"], ensure_ascii=False)
                )
                yield f"event: {event['event']}\ndata: {data_str}\n\n"
        finally:
            # 清理请求上下文，防止 contextvars 泄漏
            from src.infra.logging.context import TraceContext

            TraceContext.clear_request_context()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )


@router.get("/tools", response_model=ToolsListResponse)
async def list_tools(
    user: TokenPayload = Depends(get_current_user_required),
    agent_id: Optional[str] = Query(None, description="当前选中的 Agent ID，用于判断是否支持沙箱"),
):
    """
    获取当前用户可用的所有工具列表

    返回 Skill 工具、Human 工具和 MCP 工具的完整列表。
    MCP 工具会实际连接服务器获取工具列表、描述和参数。
    当传入 agent_id 时，根据该 Agent 是否支持沙箱来过滤沙箱类工具。
    """
    # 判断当前 Agent 是否支持沙箱
    agent_supports_sandbox = True  # 默认支持（向后兼容）
    if agent_id:
        from src.agents.core.base import _AGENT_REGISTRY

        agent_cls = _AGENT_REGISTRY.get(agent_id)
        if agent_cls:
            agent_supports_sandbox = getattr(agent_cls, "_supports_sandbox", True)
        else:
            logger.warning(
                f"[Tools API] Unknown agent_id={agent_id}, defaulting sandbox support to True"
            )

    tools = []

    # 1. Human 工具
    tools.extend(HUMAN_TOOLS)

    # 2. Sandbox MCP 管理工具（仅在沙箱模式启用且当前 Agent 支持沙箱时显示）
    if settings.ENABLE_SANDBOX and agent_supports_sandbox:
        tools.extend(SANDBOX_MCP_TOOLS)

    # 3. MCP 工具 - 使用全局单例（分布式优化）
    if settings.ENABLE_MCP:
        try:
            from src.infra.tool.mcp_global import get_global_mcp_tools

            # 使用全局单例，避免重复初始化
            mcp_tools, manager = await get_global_mcp_tools(user.sub)

            # 获取服务器名称映射（从 manager 的 _tool_server_map 或从工具名推断）
            tool_server_map = getattr(manager, "_tool_server_map", {}) if manager else {}

            # 获取用户禁用的工具列表（从 user metadata disabled_tools 字段读取）
            from src.infra.user.storage import UserStorage

            user_storage = UserStorage()
            db_user = await user_storage.get_by_id(user.sub)
            disabled_tools_raw = (
                (db_user.metadata or {}).get("disabled_tools", []) if db_user else []
            )
            disabled_tool_names = set(disabled_tools_raw)

            mcp_start_idx = len(tools)  # HUMAN tools are already in the list

            for tool in mcp_tools:
                tool_name = tool.name
                server_name = None

                # 1. 从 manager 的 tool_server_map 获取服务器名
                # 工具名可能是 "server_name:tool_name" 格式
                raw_name = tool_name
                if ":" in tool_name:
                    parts = tool_name.split(":", 1)
                    candidate_server = parts[0]
                    candidate_tool = parts[1]
                    # 在 map 中查找 (candidate_server, candidate_tool)
                    if (candidate_server, candidate_tool) in tool_server_map:
                        server_name = tool_server_map[(candidate_server, candidate_tool)]
                        raw_name = candidate_tool
                    else:
                        server_name = candidate_server
                        raw_name = candidate_tool

                # 2. 检查工具是否被用户禁用
                qualified_name = f"{server_name}:{raw_name}" if server_name else tool_name
                if qualified_name in disabled_tool_names or tool_name in disabled_tool_names:
                    continue

                # 提取工具描述
                description = tool.description if hasattr(tool, "description") else ""

                # 提取参数信息
                parameters = extract_tool_parameters(tool)

                tools.append(
                    ToolInfo(
                        name=tool_name,
                        description=description,
                        category="mcp",
                        server=server_name,
                        parameters=parameters,
                    )
                )

            # 按 MCP 工具名称排序（首字母排序），HUMAN 工具保持在前
            tools[mcp_start_idx:] = sorted(tools[mcp_start_idx:], key=lambda t: t.name.lower())

            logger.info(
                f"[Tools API] Got {len(mcp_tools)} MCP tools from global cache for user {user.sub}"
            )

        except Exception as e:
            logger.warning(f"[Tools API] Failed to get MCP tools: {e}")

    # 3. Sandbox MCP 工具 — 沙箱内运行的 MCP 服务器无法从 API 层直接发现，
    #    将每个已启用的 sandbox 服务器作为一条工具条目展示在 mcp 分类下。
    if settings.ENABLE_SANDBOX and settings.ENABLE_MCP and agent_supports_sandbox:
        try:
            from src.infra.mcp.storage import MCPStorage

            mcp_storage = MCPStorage()

            # 获取用户禁用的工具列表
            try:
                from src.infra.user.storage import UserStorage

                user_storage = UserStorage()
                db_user = await user_storage.get_by_id(user.sub)
                disabled_tool_names = set(
                    (db_user.metadata or {}).get("disabled_tools", []) if db_user else []
                )
            except Exception:
                disabled_tool_names = set()

            sandbox_servers = await mcp_storage.get_sandbox_servers(user.sub)
            for server in sandbox_servers:
                server_name = server.get("name", "")
                command = server.get("command", "")
                if not server_name or not command:
                    continue

                # 使用 server_name 作为工具名，方便与 disabled_tools 匹配
                qualified_name = f"{server_name}:sandbox_mcp"
                if qualified_name in disabled_tool_names or server_name in disabled_tool_names:
                    continue

                tools.append(
                    ToolInfo(
                        name=qualified_name,
                        description=f"MCP server in sandbox: {command}",
                        category="sandbox",
                        server=server_name,
                        parameters=[],
                    )
                )

            logger.info(
                f"[Tools API] Added {len(sandbox_servers)} sandbox MCP entries for user {user.sub}"
            )

        except Exception as e:
            logger.warning(f"[Tools API] Failed to get sandbox MCP servers: {e}")

    return ToolsListResponse(tools=tools, count=len(tools))
