"""
MCP 客户端管理器

与 Model Context Protocol 服务器通信。
支持从数据库或文件读取配置。
"""

import asyncio
import json
import logging
import os
from typing import Any, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from src.infra.tool.mcp_cache import get_cached_tools

logger = logging.getLogger(__name__)

# MCP 重试配置
MCP_MAX_RETRIES = 3
MCP_RETRY_DELAY = 1.0  # 秒
MCP_TOOL_TIMEOUT = 60  # 单次工具调用超时（秒）

# 与 deepagents backend 冲突的工具名（需要过滤掉）
CONFLICTING_TOOL_NAMES = frozenset(
    [
        "read_file",
        "write_file",
        "edit_file",
        "ls",
        "glob",
        "grep",
        "bash",
    ]
)


class MCPToolWithRetry(BaseTool):
    """
    MCP 工具包装器，添加重试逻辑

    包装原始 MCP 工具，在调用失败时自动重试。
    """

    def __init__(
        self,
        original_tool: BaseTool,
        max_retries: int = MCP_MAX_RETRIES,
        retry_delay: float = MCP_RETRY_DELAY,
    ):
        super().__init__(
            name=original_tool.name,
            description=original_tool.description,
            args_schema=original_tool.args_schema,
        )
        self._original_tool = original_tool
        self._max_retries = max_retries
        self._retry_delay = retry_delay

    def _is_retryable_error(self, error: Exception) -> bool:
        """判断错误是否可重试"""
        error_str = str(error).lower()
        retryable_patterns = [
            "429",  # rate limit
        ]
        return any(pattern in error_str for pattern in retryable_patterns)

    def _run(self, *args, **kwargs) -> Any:
        """同步运行（不支持重试，直接调用原始工具）"""
        return self._original_tool._run(*args, **kwargs)

    async def _arun(
        self, *args, config: Optional[RunnableConfig] = None, **kwargs
    ) -> Any:
        """
        异步运行（带超时和重试，失败时返回错误信息而不是抛出异常）

        即使 MCP 工具最终失败，也不会中断 Agent 执行，
        而是返回包含错误信息的字符串，让 Agent 可以继续处理。

        Args:
            *args: 位置参数
            config: LangChain RunnableConfig（可选）
            **kwargs: 关键字参数
        """
        last_error = None
        for attempt in range(self._max_retries):
            try:
                # 使用 wait_for 添加超时
                return await asyncio.wait_for(
                    self._original_tool._arun(*args, config=config, **kwargs),
                    timeout=MCP_TOOL_TIMEOUT,
                )
            except asyncio.TimeoutError:
                last_error = TimeoutError(f"Tool timed out after {MCP_TOOL_TIMEOUT}s")
                logger.warning(
                    f"MCP tool '{self.name}' timed out (attempt {attempt + 1}/{self._max_retries})"
                )
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(self._retry_delay)
                else:
                    error_msg = f"[MCP Tool Error] {self.name} timed out after {self._max_retries} attempts"
                    logger.error(error_msg)
                    return error_msg
            except Exception as e:
                last_error = e
                if self._is_retryable_error(e) and attempt < self._max_retries - 1:
                    logger.warning(
                        f"MCP tool '{self.name}' failed (attempt {attempt + 1}/{self._max_retries}): {e}. "
                        f"Retrying in {self._retry_delay}s..."
                    )
                    await asyncio.sleep(self._retry_delay)
                else:
                    # 所有重试都失败，返回错误信息而不是抛出异常
                    error_msg = f"[MCP Tool Error] {self.name} failed after {self._max_retries} attempts: {last_error}"
                    logger.error(error_msg)
                    return error_msg
        # 不应该到达这里，但以防万一
        return f"[MCP Tool Error] {self.name} failed: {last_error}"


class MCPClientManager:
    """
    MCP 客户端管理器

    管理与多个 MCP 服务器的连接，提供工具发现和调用。
    使用 langchain-mcp-adapters 实现实际的 MCP 连接。

    支持两种配置源：
    1. 数据库（推荐）：用户级配置，支持数据隔离
    2. 文件（兼容）：从 mcp.json 读取配置
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
        user_id: Optional[str] = None,
        use_database: bool = True,
    ):
        """
        初始化 MCP 客户端管理器

        Args:
            config_path: MCP 配置文件路径（仅当 use_database=False 时使用）
            user_id: 用户 ID（用于获取用户特定的 MCP 配置）
            use_database: 是否从数据库读取配置（默认 True）
        """
        self._config_path = config_path
        self._user_id = user_id
        self._use_database = use_database
        self._client: Optional[MultiServerMCPClient] = None
        self._tools: list[BaseTool] = []
        self._initialized = False

    async def initialize(self) -> None:
        """初始化 MCP 连接"""
        if self._initialized:
            return

        try:
            # 尝试从数据库读取配置
            if self._use_database:
                config = await self._load_config_from_database()
                if config:
                    logger.info(
                        f"MCP config loaded from database for user {self._user_id}: {list(config.get('mcpServers', {}).keys())}"
                    )
                    await self._initialize_with_config(config)
                    return
                else:
                    # 数据库查询成功但没有启用的服务器 - 这是用户的偏好，不应该回退到文件
                    logger.info(
                        f"No enabled MCP servers for user {self._user_id}, skipping file fallback"
                    )
                    self._initialized = True
                    return

            # 从文件读取配置（向后兼容，仅当 use_database=False 时）
            config = self._load_config_from_file()
            if config:
                await self._initialize_with_config(config)
            else:
                logger.warning("No MCP configuration found")
                self._initialized = True

        except Exception as e:
            logger.error(f"Failed to initialize MCP client: {e}")
            import traceback

            traceback.print_exc()
            self._initialized = True  # 不阻止后续执行

    async def _load_config_from_database(self) -> Optional[dict]:
        """
        从数据库加载 MCP 配置

        Returns:
            dict: 配置字典（可能包含空的 mcpServers）
            None: 数据库查询失败
        """
        try:
            from src.infra.mcp.storage import MCPStorage

            storage = MCPStorage()

            # 如果指定了 user_id，获取用户特定的配置
            # 否则只获取系统配置（用于系统级初始化）
            if self._user_id:
                config = await storage.get_effective_config(self._user_id)
                logger.info(
                    f"Loaded MCP config for user {self._user_id}: {len(config.get('mcpServers', {}))} servers"
                )
            else:
                # 没有用户 ID 时，只获取系统配置
                system_servers = await storage.list_system_servers()
                servers = {}
                for server in system_servers:
                    if server.enabled:
                        servers[server.name] = self._server_to_config_dict(server)
                config = {"mcpServers": servers}
                logger.info(f"Loaded system MCP config: {len(servers)} servers")

            # 返回配置（即使是空的），让调用者决定如何处理
            return config

        except Exception as e:
            logger.warning(f"Failed to load MCP config from database: {e}")
            import traceback

            traceback.print_exc()
            return None

    def _load_config_from_file(self) -> Optional[dict]:
        """从文件加载 MCP 配置"""
        if not os.path.exists(self._config_path):
            logger.warning(f"MCP config file not found: {self._config_path}")
            return None

        with open(self._config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        if not config.get("mcpServers"):
            logger.warning("No MCP servers configured in mcp.json")
            return None

        return config

    def _server_to_config_dict(self, server) -> dict:
        """将服务器对象转换为配置字典"""
        result = {"transport": server.transport.value}

        if server.transport.value == "stdio":
            if server.command:
                result["command"] = server.command
            if server.args:
                result["args"] = server.args
            if server.env:
                result["env"] = server.env
        else:  # sse or streamable_http
            if server.url:
                result["url"] = server.url
            if server.headers:
                result["headers"] = server.headers

        return result

    def _convert_stdio_command_for_platform(
        self, command: str, args: list[str]
    ) -> tuple[str, list[str], bool]:
        """
        转换 stdio 命令以适应当前平台

        Windows 配置（如 'cmd /c npx'）在 Linux 上需要转换为 'npx'

        Returns:
            tuple[str, list[str], bool]: (command, args, is_valid)
        """
        import shutil
        import sys

        # 只在 Linux 上处理 Windows 命令
        if sys.platform != "win32" and command == "cmd":
            # 找到实际命令（跳过 /c）
            real_args = [a for a in args if a != "/c"]
            if real_args:
                new_command = real_args[0]
                new_args = real_args[1:]
                logger.info(
                    f"Converted Windows command 'cmd {args}' to '{new_command} {new_args}' for Linux"
                )
                command, args = new_command, new_args

        # 检查命令是否存在
        if not shutil.which(command):
            logger.warning(
                f"MCP stdio command '{command}' not found in PATH, skipping this server"
            )
            return command, args, False

        return command, args, True

    async def _initialize_with_config(self, config: dict) -> None:
        """使用配置初始化 MCP 客户端（支持缓存）"""
        mcp_servers = config.get("mcpServers", {})
        if not mcp_servers:
            self._initialized = True
            return

        # 如果有 user_id，尝试使用缓存
        if self._user_id:
            tools, client = await get_cached_tools(
                user_id=self._user_id,
                config=config,
                create_client_func=self._create_mcp_client,
            )
            self._tools = tools
            self._client = client
            self._initialized = True
            return

        # 没有 user_id 时，直接创建（不使用缓存）
        tools, client = await self._create_mcp_client(config)
        self._tools = tools
        self._client = client
        self._initialized = True

    async def _create_mcp_client(
        self, config: dict
    ) -> tuple[list[BaseTool], Optional[MultiServerMCPClient]]:
        """
        创建 MCP 客户端并获取工具

        Args:
            config: MCP 配置字典

        Returns:
            tuple: (tools, client) - 工具列表和客户端
        """
        mcp_servers = config.get("mcpServers", {})
        if not mcp_servers:
            return [], None

        # 转换配置格式以适配 langchain-mcp-adapters
        server_configs = {}
        for server_name, server_config in mcp_servers.items():
            transport = server_config.get("transport", "stdio")

            if transport == "stdio":
                # stdio 传输：通过命令行启动
                command = server_config.get("command")
                args = server_config.get("args", [])

                # 转换命令以适应当前平台，并检查命令是否存在
                command, args, is_valid = self._convert_stdio_command_for_platform(
                    command, args
                )
                if not is_valid:
                    logger.warning(
                        f"Skipping MCP server '{server_name}': command not found"
                    )
                    continue

                server_configs[server_name] = {
                    "command": command,
                    "args": args,
                    "transport": "stdio",
                }
                # 添加环境变量
                if server_config.get("env"):
                    server_configs[server_name]["env"] = server_config["env"]
            elif transport in ("sse", "streamable_http"):
                # HTTP 传输：SSE 或 streamable HTTP
                server_configs[server_name] = {
                    "url": server_config.get("url"),
                    "transport": transport,
                }
                # 添加 headers（如 Authorization）
                if server_config.get("headers"):
                    server_configs[server_name]["headers"] = server_config["headers"]

        # 创建 MultiServerMCPClient
        client = MultiServerMCPClient(server_configs)

        # 获取所有工具（带错误处理，跳过失败的服务器）
        try:
            tools = await client.get_tools()
            logger.info(
                f"MCP client initialized with {len(tools)} tools from {len(mcp_servers)} servers"
            )
            return tools, client
        except Exception as e:
            logger.warning(
                f"Some MCP servers failed to initialize, partial tools may be available: {e}"
            )
            return [], client

    async def _connect_server(self, name: str, config: dict) -> None:
        """连接到单个 MCP 服务器（已弃用，由 MultiServerMCPClient 统一管理）"""
        pass

    async def get_tools(self) -> list[BaseTool]:
        """
        获取所有可用的 MCP 工具（带重试包装）

        每个工具都被包装在 MCPToolWithRetry 中，提供自动重试能力。
        会过滤掉与 deepagents backend 冲突的工具名。
        """
        if not self._initialized:
            await self.initialize()

        # 过滤掉与 deepagents backend 冲突的工具
        filtered_tools = []
        skipped_tools = []
        for tool in self._tools:
            if tool.name in CONFLICTING_TOOL_NAMES:
                skipped_tools.append(tool.name)
            else:
                filtered_tools.append(tool)

        if skipped_tools:
            logger.info(f"[MCP] Filtered out conflicting tools: {skipped_tools}")

        # 包装工具以添加重试逻辑
        return [MCPToolWithRetry(tool) for tool in filtered_tools]

    def _is_mcp_retryable_error(self, error: Exception) -> bool:
        """判断 MCP 错误是否可重试"""
        error_str = str(error).lower()
        # 参数错误、超时、连接错误等可重试
        retryable_patterns = [
            "429",  # rate limit
        ]
        return any(pattern in error_str for pattern in retryable_patterns)

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """
        调用 MCP 工具（带重试，失败时返回错误信息）

        Args:
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            工具执行结果，或错误信息字符串
        """
        for tool in self._tools:
            if tool.name == tool_name:
                last_error = None
                for attempt in range(MCP_MAX_RETRIES):
                    try:
                        return await tool.ainvoke(arguments)
                    except Exception as e:
                        last_error = e
                        if (
                            self._is_mcp_retryable_error(e)
                            and attempt < MCP_MAX_RETRIES - 1
                        ):
                            logger.warning(
                                f"MCP tool '{tool_name}' failed (attempt {attempt + 1}/{MCP_MAX_RETRIES}): {e}. "
                                f"Retrying in {MCP_RETRY_DELAY}s..."
                            )
                            await asyncio.sleep(MCP_RETRY_DELAY)
                        else:
                            # 所有重试都失败，返回错误信息
                            error_msg = f"[MCP Tool Error] {tool_name} failed after {MCP_MAX_RETRIES} attempts: {last_error}"
                            logger.error(error_msg)
                            return error_msg
                # 不应该到达这里
                return f"[MCP Tool Error] {tool_name} failed: {last_error}"
        return f"[MCP Tool Error] Tool '{tool_name}' not found"

    async def close(self) -> None:
        """关闭所有 MCP 连接"""
        # MultiServerMCPClient 的连接会在对象销毁时自动清理
        self._client = None
        self._tools.clear()
        self._initialized = False


class MCPClient:
    """
    MCP 客户端（简化版）

    与单个 MCP 服务器通信。包装 MCPClientManager 提供简化的 API。
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
        user_id: Optional[str] = None,
        use_database: bool = True,
    ):
        self._manager = MCPClientManager(config_path, user_id, use_database)
        self._initialized = False

    async def connect(self, server_name: str) -> None:
        """连接到 MCP 服务器"""
        if not self._initialized:
            await self._manager.initialize()
            self._initialized = True

    async def disconnect(self, server_name: str) -> None:
        """断开与 MCP 服务器的连接"""
        await self._manager.close()
        self._initialized = False

    async def list_tools(self, server_name: Optional[str] = None) -> list[dict]:
        """列出 MCP 服务器提供的工具"""
        if not self._initialized:
            await self._manager.initialize()
            self._initialized = True

        tools = self._manager._tools
        if server_name:
            # 过滤特定服务器的工具
            return [{"name": t.name, "description": t.description} for t in tools]
        return [{"name": t.name, "description": t.description} for t in tools]

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict,
    ) -> Any:
        """调用 MCP 工具"""
        if not self._initialized:
            await self._manager.initialize()
            self._initialized = True
        return await self._manager.call_tool(tool_name, arguments)

    async def list_resources(self, server_name: str) -> list[dict]:
        """列出 MCP 服务器提供的资源"""
        # langchain-mcp-adapters 不直接暴露 resources API
        return []

    async def read_resource(
        self,
        server_name: str,
        resource_uri: str,
    ) -> Any:
        """读取 MCP 资源"""
        # langchain-mcp-adapters 不直接暴露 resources API
        return None
