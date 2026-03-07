"""
Agent 路由

提供 Agent 列表和流式聊天接口。
每个 Agent 就是一个 Graph，流式请求接入 graph 后输出 SSE 事件。
"""

import logging
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from src.agents.core.base import AgentFactory
from src.api.deps import get_current_user_optional, get_current_user_required
from src.kernel.config import settings
from src.kernel.schemas.agent import (
    AgentRequest,
    ToolInfo,
    ToolParamInfo,
    ToolsListResponse,
)
from src.kernel.schemas.user import TokenPayload

router = APIRouter()
logger = logging.getLogger(__name__)

# 内置工具定义（带参数）
BUILTIN_TOOLS = [
    ToolInfo(
        name="read_file",
        description="读取文件内容",
        category="builtin",
        parameters=[
            ToolParamInfo(name="file_path", type="string", description="文件路径", required=True),
        ],
    ),
    ToolInfo(
        name="write_file",
        description="写入文件",
        category="builtin",
        parameters=[
            ToolParamInfo(name="file_path", type="string", description="文件路径", required=True),
            ToolParamInfo(name="content", type="string", description="文件内容", required=True),
        ],
    ),
    ToolInfo(
        name="edit_file",
        description="编辑文件",
        category="builtin",
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
        category="builtin",
        parameters=[
            ToolParamInfo(name="path", type="string", description="目录路径", required=False),
        ],
    ),
    ToolInfo(
        name="glob",
        description="按模式搜索文件",
        category="builtin",
        parameters=[
            ToolParamInfo(name="pattern", type="string", description="glob 模式", required=True),
            ToolParamInfo(name="path", type="string", description="搜索路径", required=False),
        ],
    ),
    ToolInfo(
        name="grep",
        description="在文件中搜索内容",
        category="builtin",
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
        category="builtin",
        parameters=[
            ToolParamInfo(name="command", type="string", description="要执行的命令", required=True),
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

# Reveal File 工具定义
REVEAL_FILE_TOOLS = [
    ToolInfo(
        name="reveal_file",
        description="向用户展示/推荐一个文件，前端会自动展开文件树并显示可点击的文件路径",
        category="builtin",
        parameters=[
            ToolParamInfo(
                name="path",
                type="string",
                description="要展示的文件路径（绝对路径或相对于工作目录的路径）",
                required=True,
            ),
            ToolParamInfo(
                name="description",
                type="string",
                description="对文件内容的简要描述，帮助用户理解为什么要查看这个文件",
                required=False,
            ),
        ],
    ),
]

# Add Skill 工具定义
ADD_SKILL_TOOLS = [
    ToolInfo(
        name="add_skill_from_path",
        description="从 backend 目录导入 skill 到用户的 skill 列表。读取指定目录中的所有文件（包括 SKILL.md 和依赖文件），创建为用户的 skill。导入成功后，前端会自动刷新 skill 列表。",
        category="builtin",
        parameters=[
            ToolParamInfo(
                name="skill_path",
                type="string",
                description="skill 目录路径（相对于工作目录或绝对路径），目录中应该包含 SKILL.md 文件作为主文件",
                required=True,
            ),
            ToolParamInfo(
                name="skill_name",
                type="string",
                description="自定义 skill 名称（可选，默认从 SKILL.md 解析）",
                required=False,
            ),
            ToolParamInfo(
                name="description",
                type="string",
                description="skill 描述（可选，默认从 SKILL.md 解析）",
                required=False,
            ),
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
async def list_agents():
    """列出所有可用的 Agent（按名称排序，默认 agent 排在最前面）"""
    return {
        "agents": AgentFactory.list_agents(default_agent_id=settings.DEFAULT_AGENT),
        "default_agent": settings.DEFAULT_AGENT,
    }


@router.post("/{agent_id}/chat")
async def chat(
    agent_id: str,
    request: AgentRequest,
    user: TokenPayload = Depends(get_current_user_optional),
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
    # request.base_url 返回的是 base URL（如 http://localhost:8000/），需要去掉末尾的 /
    base_url = str(request.base_url).rstrip("/")

    # Pass all agent_options to the agent
    agent_options = request_body.agent_options or {}
    logger.info(f"[API] request.agent_options: {request_body.agent_options}")
    logger.info(f"[API] agent_options to pass: {agent_options}")
    logger.info(f"[API] disabled_tools: {request_body.disabled_tools}")

    async def event_generator():
        async for event in agent.stream(
            request_body.message,
            session_id,
            user_id=user_id,
            disabled_tools=request_body.disabled_tools,
            agent_options=agent_options,
            base_url=base_url,
        ):
            # event 格式: {"event": "xxx", "data": {...}}
            yield f"event: {event['event']}\ndata: {event['data']}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )


@router.get("/tools", response_model=ToolsListResponse)
async def list_tools(
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    获取当前用户可用的所有工具列表

    返回 Skill 工具、Human 工具和 MCP 工具的完整列表。
    MCP 工具会实际连接服务器获取工具列表、描述和参数。
    """
    tools = []

    # 1. Human 工具
    tools.extend(HUMAN_TOOLS)

    # 2. Reveal File 工具
    if settings.ENABLE_SANDBOX:
        tools.extend(REVEAL_FILE_TOOLS)

    # 3. Add Skill 工具
    if settings.ENABLE_SANDBOX:
        tools.extend(ADD_SKILL_TOOLS)

    # 4. MCP 工具（实际连接获取工具列表）
    if settings.ENABLE_MCP:
        mcp_manager = None
        try:
            from src.infra.tool.mcp_client import MCPClientManager

            # 使用缓存机制，避免每次都重新连接
            # 缓存会在以下情况自动失效：
            # 1. 用户修改 MCP 配置时
            # 2. 管理员修改系统配置时
            # 3. 配置哈希变更时
            # 4. 30 分钟 TTL 过期
            mcp_manager = MCPClientManager(
                user_id=user.sub,
            )
            await mcp_manager.initialize()
            mcp_tools = await mcp_manager.get_tools()

            # 获取服务器名称映射（从工具名推断）
            # MCP 工具名格式通常是 "server_name:tool_name" 或直接是 tool_name
            for tool in mcp_tools:
                tool_name = tool.name
                server_name = None

                # 尝试从工具名提取服务器名
                if ":" in tool_name:
                    parts = tool_name.split(":", 1)
                    server_name = parts[0]
                    # 保持原始工具名（用户选择时使用原始名）

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

            logger.info(f"Loaded {len(mcp_tools)} MCP tools for user {user.sub}")

        except Exception as e:
            logger.warning(f"Failed to get MCP tools: {e}")
        # 注意：不要在这里关闭 mcp_manager
        # 让缓存的客户端保持连接，下次请求可以复用

    return ToolsListResponse(tools=tools, count=len(tools))
