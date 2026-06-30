"""
MCP server storage using MongoDB

Supports both system-level and user-level MCP server configurations.
"""

import copy
import inspect
from typing import TYPE_CHECKING, Any, Mapping, Optional

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.mcp.encryption import (
    decrypt_server_secrets,
    encrypt_server_secrets,
    encrypt_value,
)
from src.infra.mcp.storage_helpers import (
    MCP_DISCOVER_TOOL_LIMIT,
    MCP_DISCOVER_TOOL_PARAMETER_LIMIT,
    MCP_PREFERENCE_LIST_LIMIT,
    MCP_SERVER_LIST_LIMIT,
    MCP_TOOL_POLICY_LIST_LIMIT,
    SENSITIVE_ENV_PATTERNS,
    _apply_disabled_tool_update,
    _normalize_disabled_tools,
)
from src.infra.mcp.storage_operations import StorageOperations, _can_access_system_server
from src.infra.storage.mongodb import get_mongo_client
from src.infra.utils.datetime import to_iso, utc_now_iso
from src.kernel.config import settings
from src.kernel.schemas.mcp import (
    MCPRoleQuota,
    MCPServerResponse,
    MCPToolPolicy,
    MCPTransport,
    SystemMCPServer,
    UserMCPServer,
)

logger = get_logger(__name__)


if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection


class MCPStorage(StorageOperations):
    """
    MCP server storage

    Supports system-level (admin managed) and user-level configurations.
    User preferences allow users to override enabled state of system servers.
    """

    def __init__(self):
        self._client: Optional["AsyncIOMotorClient"] = None
        self._system_collection: Optional["AsyncIOMotorCollection"] = None
        self._user_collection: Optional["AsyncIOMotorCollection"] = None
        self._preferences_collection: Optional["AsyncIOMotorCollection"] = None
        self._tool_preferences_collection: Optional["AsyncIOMotorCollection"] = None
        self._tool_policies_collection: Optional["AsyncIOMotorCollection"] = None

    async def _invalidate_user_cache(self, user_id: str) -> None:
        """Invalidate MCP tools cache for a specific user"""
        from src.infra.tool.mcp_global import invalidate_global_cache

        await invalidate_global_cache(user_id)
        logger.info(f"[MCP Storage] Invalidated global cache for user {user_id}")

    async def _invalidate_all_cache(self) -> None:
        """Invalidate MCP tools cache for all users (system config changed)"""
        from src.infra.tool.mcp_global import invalidate_all_global_cache

        count = await invalidate_all_global_cache()
        logger.info(f"[MCP Storage] Invalidated all global cache, {count} entries")

    async def _call_optional_async(self, value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    def _get_system_collection(self) -> "AsyncIOMotorCollection":
        """Get system MCP servers collection lazily"""
        if self._system_collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._system_collection = db["system_mcp_servers"]
        return self._system_collection

    def _get_user_collection(self) -> "AsyncIOMotorCollection":
        """Get user MCP servers collection lazily"""
        if self._user_collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._user_collection = db["user_mcp_servers"]
        return self._user_collection

    def _get_preferences_collection(self) -> "AsyncIOMotorCollection":
        """Get user MCP preferences collection lazily"""
        if self._preferences_collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._preferences_collection = db["user_mcp_preferences"]
        return self._preferences_collection

    def _get_tool_preferences_collection(self) -> "AsyncIOMotorCollection":
        """Get user MCP tool preferences collection lazily"""
        if self._tool_preferences_collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._tool_preferences_collection = db["user_mcp_tool_preferences"]
        return self._tool_preferences_collection

    def _get_tool_policies_collection(self) -> "AsyncIOMotorCollection":
        """Get admin-managed MCP tool policies collection lazily."""
        if self._tool_policies_collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._tool_policies_collection = db["mcp_tool_policies"]
        return self._tool_policies_collection

    # ==========================================
    # System MCP Servers (Admin)
    # ==========================================

    async def list_system_servers(self) -> list[SystemMCPServer]:
        """List all system MCP servers"""
        collection = self._get_system_collection()
        servers = []
        async for doc in collection.find({}).limit(MCP_SERVER_LIST_LIMIT):
            servers.append(await self._doc_to_system_server_async(doc))
        return servers

    async def get_system_server(self, name: str) -> Optional[SystemMCPServer]:
        """Get a system MCP server by name"""
        collection = self._get_system_collection()
        doc = await collection.find_one({"name": name})
        if doc:
            return await self._doc_to_system_server_async(doc)
        return None

    async def create_system_server(self, server, admin_user_id: str) -> SystemMCPServer:
        """Create a system MCP server (admin only)"""
        collection = self._get_system_collection()

        now = utc_now_iso()
        doc = {
            "name": server.name,
            "transport": server.transport.value,
            "enabled": server.enabled,
            "url": server.url,
            "headers": server.headers,
            "command": server.command,
            "env_keys": server.env_keys,
            "is_system": True,
            "allowed_roles": getattr(server, "allowed_roles", []),
            "role_quotas": {
                role_name: quota.model_dump() if hasattr(quota, "model_dump") else quota
                for role_name, quota in getattr(server, "role_quotas", {}).items()
            },
            "created_at": now,
            "updated_at": now,
            "updated_by": admin_user_id,
            "created_by": admin_user_id,
        }

        # 加密敏感字段
        doc = await run_blocking_io(encrypt_server_secrets, doc)

        await collection.insert_one(doc)

        # Invalidate all caches since system server affects all users
        await self._invalidate_all_cache()

        return await self._doc_to_system_server_async(doc)

    async def update_system_server(
        self, name: str, updates, admin_user_id: str
    ) -> Optional[SystemMCPServer]:
        """Update a system MCP server (admin only)"""
        collection = self._get_system_collection()

        doc = await collection.find_one({"name": name})
        if not doc:
            return None

        update_data: dict[str, Any] = {
            "updated_at": utc_now_iso(),
            "updated_by": admin_user_id,
        }

        if updates.transport is not None:
            update_data["transport"] = updates.transport.value
        if updates.enabled is not None:
            update_data["enabled"] = updates.enabled
        if updates.url is not None:
            update_data["url"] = updates.url
        if updates.headers is not None:
            update_data["headers"] = (
                await run_blocking_io(encrypt_value, updates.headers)
                if updates.headers
                else updates.headers
            )
        if updates.command is not None:
            update_data["command"] = updates.command
        if updates.env_keys is not None:
            update_data["env_keys"] = updates.env_keys
        if updates.allowed_roles is not None:
            update_data["allowed_roles"] = updates.allowed_roles
        if updates.role_quotas is not None:
            update_data["role_quotas"] = {
                role_name: quota.model_dump() for role_name, quota in updates.role_quotas.items()
            }

        await collection.update_one({"name": name}, {"$set": update_data})

        # Invalidate all caches since system server affects all users
        await self._invalidate_all_cache()

        updated_doc = await collection.find_one({"name": name})
        return await self._doc_to_system_server_async(updated_doc) if updated_doc else None

    async def delete_system_server(self, name: str) -> bool:
        """Delete a system MCP server (admin only)"""
        collection = self._get_system_collection()
        result = await collection.delete_one({"name": name})

        # Invalidate all caches since system server affects all users
        if result.deleted_count > 0:
            await self._invalidate_all_cache()

        return result.deleted_count > 0

    # ==========================================
    # User MCP Servers
    # ==========================================

    async def list_user_servers(self, user_id: str) -> list[UserMCPServer]:
        """List all MCP servers for a specific user"""
        collection = self._get_user_collection()
        servers = []
        async for doc in collection.find({"user_id": user_id}).limit(MCP_SERVER_LIST_LIMIT):
            servers.append(await self._doc_to_user_server_async(doc))
        return servers

    async def get_user_server(self, name: str, user_id: str) -> Optional[UserMCPServer]:
        """Get a user's MCP server by name"""
        collection = self._get_user_collection()
        doc = await collection.find_one({"name": name, "user_id": user_id})
        if doc:
            return await self._doc_to_user_server_async(doc)
        return None

    async def create_user_server(self, server, user_id: str) -> UserMCPServer:
        """Create a user MCP server"""
        collection = self._get_user_collection()

        now = utc_now_iso()
        doc = {
            "name": server.name,
            "transport": server.transport.value,
            "enabled": server.enabled,
            "url": server.url,
            "headers": server.headers,
            "command": server.command,
            "env_keys": server.env_keys,
            "user_id": user_id,
            "is_system": False,
            "created_at": now,
            "updated_at": now,
        }

        # 加密敏感字段
        doc = await run_blocking_io(encrypt_server_secrets, doc)

        await collection.insert_one(doc)

        # Invalidate cache for this user
        await self._invalidate_user_cache(user_id)

        return await self._doc_to_user_server_async(doc)

    async def update_user_server(self, name: str, updates, user_id: str) -> Optional[UserMCPServer]:
        """Update a user MCP server"""
        collection = self._get_user_collection()

        doc = await collection.find_one({"name": name, "user_id": user_id})
        if not doc:
            return None

        update_data: dict[str, Any] = {"updated_at": utc_now_iso()}

        if updates.transport is not None:
            update_data["transport"] = updates.transport.value
        if updates.enabled is not None:
            update_data["enabled"] = updates.enabled
        if updates.url is not None:
            update_data["url"] = updates.url
        if updates.headers is not None:
            update_data["headers"] = (
                await run_blocking_io(encrypt_value, updates.headers)
                if updates.headers
                else updates.headers
            )
        if updates.command is not None:
            update_data["command"] = updates.command
        if updates.env_keys is not None:
            update_data["env_keys"] = updates.env_keys

        await collection.update_one({"name": name, "user_id": user_id}, {"$set": update_data})

        # Invalidate cache for this user
        await self._invalidate_user_cache(user_id)

        updated_doc = await collection.find_one({"name": name, "user_id": user_id})
        return await self._doc_to_user_server_async(updated_doc) if updated_doc else None

    async def delete_user_server(self, name: str, user_id: str) -> bool:
        """Delete a user MCP server"""
        collection = self._get_user_collection()
        result = await collection.delete_one({"name": name, "user_id": user_id})

        # Invalidate cache for this user
        if result.deleted_count > 0:
            await self._invalidate_user_cache(user_id)

        return result.deleted_count > 0

    # ==========================================
    # User Preferences (for system servers)
    # ==========================================

    async def _get_user_preferences(self, user_id: str) -> dict[str, bool]:
        """Get user's enabled preferences for system servers"""
        collection = self._get_preferences_collection()
        preferences = {}
        async for doc in collection.find({"user_id": user_id}).limit(MCP_PREFERENCE_LIST_LIMIT):
            preferences[doc["server_name"]] = doc.get("enabled", True)
        logger.info(f"[MCP] Retrieved preferences for user {user_id}: {preferences}")
        return preferences

    async def _set_user_preference(self, server_name: str, user_id: str, enabled: bool) -> None:
        """Set user's preference for a system server"""
        collection = self._get_preferences_collection()
        await collection.update_one(
            {"server_name": server_name, "user_id": user_id},
            {
                "$set": {
                    "enabled": enabled,
                    "updated_at": utc_now_iso(),
                }
            },
            upsert=True,
        )
        logger.info(
            f"[MCP] Set preference for user {user_id}, server {server_name}: enabled={enabled}"
        )

        # Invalidate cache for this user
        await self._invalidate_user_cache(user_id)

    # ==========================================
    # Tool Discovery & Tool-level Preferences
    # ==========================================

    async def discover_server_tools(
        self,
        server_name: str,
        user_id: str,
        user_roles: list[str] | None = None,
        is_admin: bool = False,
    ) -> tuple[list[dict[str, Any]], Optional[str]]:
        """
        Discover tools available from a specific MCP server.

        Connects to the server and lists its tools without caching.
        Returns (tools_list, error_message).
        """
        manager = None
        try:
            # Find the server config (user or system)
            server: UserMCPServer | SystemMCPServer | None = await self.get_user_server(
                server_name, user_id
            )
            if not server:
                server = await self.get_system_server(server_name)
                # Check role-based access for system servers
                if server and not _can_access_system_server(
                    getattr(server, "allowed_roles", []),
                    user_roles,
                    is_admin=is_admin,
                ):
                    return [], f"Server '{server_name}' not found"
            if not server:
                return [], f"Server '{server_name}' not found"

            # Get server-level disabled tools (system servers)
            system_disabled_tools = await self.get_system_disabled_tools()
            server_disabled_tools = system_disabled_tools.get(server_name, set())

            # For user servers, check the server's own disabled_tools
            if not server.is_system and hasattr(server, "disabled_tools"):
                server_disabled_tools = set(server.disabled_tools)

            # Get user-disabled tools for this server (per-user preference)
            user_disabled_tool_names = await self.get_disabled_tool_names(user_id)
            tool_policies = await self.list_tool_policies(server_name)

            from src.infra.tool.mcp_client import MCPClientManager

            manager = MCPClientManager(use_database=False)

            # Build config for just this one server
            config_dict = self._server_to_config_dict_static(server)
            config = {"mcpServers": {server_name: config_dict}}

            # Bypass initialize() which tries to load from file/database,
            # directly use _initialize_with_config with our custom config
            await manager._initialize_with_config(config)
            tools = manager._tools

            result = []
            for index, tool in enumerate(tools):
                if index >= MCP_DISCOVER_TOOL_LIMIT:
                    break
                # langchain-mcp-adapters may prefix with "server_name:"
                # Strip it so the frontend can construct the qualified name itself
                tool_name = tool.name
                if tool_name.startswith(f"{server_name}:"):
                    tool_name = tool_name[len(server_name) + 1 :]

                # Check if this tool is system-disabled
                is_system_disabled = tool_name in server_disabled_tools

                # Check if this tool is user-disabled (qualified name: server:tool)
                qualified = f"{server_name}:{tool_name}"
                is_user_disabled = qualified in user_disabled_tool_names
                policy = tool_policies.get(tool_name)

                tool_info: dict[str, Any] = {
                    "name": tool_name,
                    "description": getattr(tool, "description", ""),
                    "parameters": [],
                    "system_disabled": bool(policy.disabled) if policy else is_system_disabled,
                    "user_disabled": is_user_disabled,
                    "allowed_roles": list(policy.allowed_roles) if policy else [],
                    "role_quotas": policy.role_quotas if policy else {},
                    "policy_configured": policy is not None,
                    "inline_exposure": bool(policy.inline_exposure) if policy else False,
                }
                # Extract parameters if possible
                try:
                    if hasattr(tool, "args_schema") and tool.args_schema:
                        if isinstance(tool.args_schema, dict):
                            schema = tool.args_schema
                        else:
                            schema = tool.args_schema.schema()
                        properties = schema.get("properties", {})
                        required = set(schema.get("required", []))
                        for index, (param_name, param_info) in enumerate(properties.items()):
                            if index >= MCP_DISCOVER_TOOL_PARAMETER_LIMIT:
                                break
                            if isinstance(param_info, dict):
                                tool_info["parameters"].append(
                                    {
                                        "name": param_name,
                                        "type": param_info.get("type", "string"),
                                        "description": param_info.get("description", ""),
                                        "required": param_name in required,
                                        "default": param_info.get("default"),
                                    }
                                )
                except Exception:
                    pass
                result.append(tool_info)

            return result, None

        except Exception as e:
            logger.error(f"[MCP] Failed to discover tools for server '{server_name}': {e}")
            return [], str(e)
        finally:
            if manager:
                await manager.close()

    def _server_to_config_dict_static(self, server) -> dict[str, Any]:
        """Convert a server object to config dict (static method style)"""
        result = {"transport": server.transport.value}
        if server.url:
            result["url"] = server.url
        if server.headers:
            result["headers"] = server.headers
        if server.command:
            result["command"] = server.command
        if server.env_keys:
            result["env_keys"] = server.env_keys
        return result

    async def get_tool_preferences(self, user_id: str) -> dict[str, bool]:
        """
        Get user's tool-level preferences.

        Returns a dict mapping fully qualified tool name (server_name:tool_name or tool_name)
        to enabled status. Only disabled tools are stored, so missing keys mean enabled.
        """
        collection = self._get_tool_preferences_collection()
        preferences: dict[str, bool] = {}
        async for doc in collection.find({"user_id": user_id}).limit(MCP_PREFERENCE_LIST_LIMIT):
            tool_key = doc["tool_name"]
            enabled = doc.get("enabled", True)
            if not enabled:
                preferences[tool_key] = False
        return preferences

    async def set_tool_preference(
        self, tool_name: str, server_name: str, user_id: str, enabled: bool
    ) -> None:
        """
        Set user's preference for a specific MCP tool.

        Args:
            tool_name: The tool name (without server prefix)
            server_name: The MCP server name
            user_id: The user's ID
            enabled: Whether the tool is enabled
        """
        collection = self._get_tool_preferences_collection()
        # Use a composite key: server_name:tool_name for uniqueness
        qualified_name = f"{server_name}:{tool_name}"
        await collection.update_one(
            {"tool_name": qualified_name, "user_id": user_id},
            {
                "$set": {
                    "tool_name": qualified_name,
                    "server_name": server_name,
                    "tool_base_name": tool_name,
                    "enabled": enabled,
                    "updated_at": utc_now_iso(),
                }
            },
            upsert=True,
        )
        # Invalidate MCP tools cache for this user
        await self._invalidate_user_cache(user_id)

    async def get_disabled_tool_names(self, user_id: str) -> set[str]:
        """Get set of fully qualified tool names that are disabled by the user."""
        prefs = await self.get_tool_preferences(user_id)
        return {name for name, enabled in prefs.items() if not enabled}

    async def set_tool_policy(
        self,
        *,
        server_name: str,
        tool_name: str,
        allowed_roles: list[str] | None = None,
        role_quotas: Mapping[str, MCPRoleQuota | dict[str, Any]] | None = None,
        disabled: bool | None = None,
        inline_exposure: bool | None = None,
        updated_by: str | None = None,
    ) -> MCPToolPolicy:
        """Create or update an admin-managed policy for one MCP tool."""
        collection = self._get_tool_policies_collection()
        existing = await collection.find_one({"server_name": server_name, "tool_name": tool_name})
        now = utc_now_iso()
        update_data: dict[str, Any] = {
            "server_name": server_name,
            "tool_name": tool_name,
            "updated_at": now,
            "updated_by": updated_by,
        }
        if not existing:
            update_data["created_at"] = now
        if allowed_roles is not None:
            update_data["allowed_roles"] = allowed_roles
        if role_quotas is not None:
            update_data["role_quotas"] = {
                role_name: quota.model_dump() if hasattr(quota, "model_dump") else quota
                for role_name, quota in role_quotas.items()
            }
        if disabled is not None:
            update_data["disabled"] = disabled
        if inline_exposure is not None:
            update_data["inline_exposure"] = inline_exposure

        await collection.update_one(
            {"server_name": server_name, "tool_name": tool_name},
            {"$set": update_data},
            upsert=True,
        )

        await self._call_optional_async(self._invalidate_all_cache())
        policy = await self.get_tool_policy(server_name, tool_name)
        if policy is None:
            return MCPToolPolicy(**update_data)
        return policy

    async def get_tool_policy(self, server_name: str, tool_name: str) -> MCPToolPolicy | None:
        """Get the explicit policy for one MCP tool, if configured."""
        collection = self._get_tool_policies_collection()
        doc = await collection.find_one({"server_name": server_name, "tool_name": tool_name})
        if not doc:
            return None
        return self._doc_to_tool_policy(doc)

    async def list_tool_policies(self, server_name: str) -> dict[str, MCPToolPolicy]:
        """List explicit tool policies for a server, keyed by tool name."""
        collection = self._get_tool_policies_collection()
        policies: dict[str, MCPToolPolicy] = {}
        async for doc in collection.find({"server_name": server_name}).limit(
            MCP_TOOL_POLICY_LIST_LIMIT
        ):
            policy = self._doc_to_tool_policy(doc)
            if policy.tool_name:
                policies[policy.tool_name] = policy
        return policies

    async def list_tool_policies_for_servers(
        self,
        server_names: list[str],
    ) -> dict[str, dict[str, MCPToolPolicy]]:
        """List explicit tool policies for multiple servers in one query."""
        if not server_names:
            return {}

        collection = self._get_tool_policies_collection()
        policies_by_server: dict[str, dict[str, MCPToolPolicy]] = {}
        async for doc in collection.find({"server_name": {"$in": server_names}}).limit(
            MCP_TOOL_POLICY_LIST_LIMIT
        ):
            policy = self._doc_to_tool_policy(doc)
            if not policy.server_name or not policy.tool_name:
                continue
            policies_by_server.setdefault(policy.server_name, {})[policy.tool_name] = policy
        return policies_by_server

    async def set_system_tool_disabled(
        self, server_name: str, tool_name: str, disabled: bool
    ) -> None:
        """
        Set system-level tool disabled status (admin only).

        Args:
            server_name: The MCP server name
            tool_name: The tool name (without server prefix)
            disabled: Whether the tool is disabled at system level
        """
        collection = self._get_system_collection()
        server_doc = await collection.find_one({"name": server_name})
        if not server_doc:
            raise ValueError(f"System server '{server_name}' not found")

        disabled_tools = _apply_disabled_tool_update(
            server_doc.get("disabled_tools", []),
            tool_name,
            disabled,
        )

        await collection.update_one(
            {"name": server_name},
            {
                "$set": {
                    "disabled_tools": disabled_tools,
                    "updated_at": utc_now_iso(),
                }
            },
        )

        # Invalidate all caches since system-level change affects all users
        await self._invalidate_all_cache()

    async def get_system_disabled_tools(self) -> dict[str, set[str]]:
        """
        Get all system-disabled tools grouped by server.

        Returns:
            Dict mapping server_name to set of disabled tool names
        """
        collection = self._get_system_collection()
        result: dict[str, set[str]] = {}
        async for doc in collection.find({}).limit(MCP_SERVER_LIST_LIMIT):
            server_name = doc["name"]
            disabled_tools = _normalize_disabled_tools(doc.get("disabled_tools", []))
            if disabled_tools:
                result[server_name] = set(disabled_tools)
        return result

    async def set_user_server_tool_disabled(
        self, server_name: str, tool_name: str, user_id: str, disabled: bool
    ) -> None:
        """
        Set tool disabled status on a user-owned MCP server.
        This is a server-level change that affects the tool's availability.

        Args:
            server_name: The MCP server name
            tool_name: The tool name (without server prefix)
            user_id: The server owner's user ID
            disabled: Whether the tool is disabled
        """
        collection = self._get_user_collection()
        server_doc = await collection.find_one({"name": server_name, "user_id": user_id})
        if not server_doc:
            raise ValueError(f"User server '{server_name}' not found for user '{user_id}'")

        disabled_tools = _apply_disabled_tool_update(
            server_doc.get("disabled_tools", []),
            tool_name,
            disabled,
        )

        await collection.update_one(
            {"name": server_name, "user_id": user_id},
            {
                "$set": {
                    "disabled_tools": disabled_tools,
                    "updated_at": utc_now_iso(),
                }
            },
        )

        # Invalidate caches
        await self._invalidate_user_cache(user_id)

    async def get_user_server_disabled_tools(self, user_id: str) -> dict[str, set[str]]:
        """
        Get disabled tools for all user-owned servers.

        Returns:
            Dict mapping server_name to set of disabled tool names
        """
        collection = self._get_user_collection()
        result: dict[str, set[str]] = {}
        async for doc in collection.find({"user_id": user_id}).limit(MCP_SERVER_LIST_LIMIT):
            server_name = doc["name"]
            disabled_tools = _normalize_disabled_tools(doc.get("disabled_tools", []))
            if disabled_tools:
                result[server_name] = set(disabled_tools)
        return result

    # ==========================================
    # Document Conversion
    # ==========================================

    async def _decrypt_server_secrets_async(self, doc: dict[str, Any]) -> dict[str, Any]:
        return await run_blocking_io(decrypt_server_secrets, doc)

    async def _doc_to_system_server_async(self, doc: dict[str, Any]) -> SystemMCPServer:
        return self._doc_to_system_server(await self._decrypt_server_secrets_async(doc))

    async def _doc_to_user_server_async(self, doc: dict[str, Any]) -> UserMCPServer:
        return self._doc_to_user_server(await self._decrypt_server_secrets_async(doc))

    async def _doc_to_response_async(
        self,
        doc: dict[str, Any],
        is_system: bool,
        can_edit: bool,
        hide_sensitive: bool = False,
    ) -> MCPServerResponse:
        return self._doc_to_response(
            await self._decrypt_server_secrets_async(doc),
            is_system=is_system,
            can_edit=can_edit,
            hide_sensitive=hide_sensitive,
            already_decrypted=True,
        )

    async def _doc_to_config_dict_async(self, doc: dict[str, Any]) -> dict[str, Any]:
        return self._doc_to_config_dict(
            await self._decrypt_server_secrets_async(doc), already_decrypted=True
        )

    def _doc_to_system_server(self, doc: dict[str, Any]) -> SystemMCPServer:
        """Convert MongoDB document to SystemMCPServer"""
        created_at = doc.get("created_at")
        updated_at = doc.get("updated_at")

        if created_at and hasattr(created_at, "isoformat"):
            created_at = to_iso(created_at)
        if updated_at and hasattr(updated_at, "isoformat"):
            updated_at = to_iso(updated_at)

        return SystemMCPServer(
            name=doc["name"],
            transport=MCPTransport._value2member_map_.get(
                doc.get("transport", "streamable_http"),
                MCPTransport.STREAMABLE_HTTP,
            ),
            enabled=doc.get("enabled", True),
            url=doc.get("url"),
            headers=doc.get("headers"),
            command=doc.get("command"),
            env_keys=doc.get("env_keys"),
            is_system=True,
            disabled_tools=_normalize_disabled_tools(doc.get("disabled_tools", [])),
            allowed_roles=doc.get("allowed_roles", []),
            role_quotas=doc.get("role_quotas", {}),
            created_at=created_at,
            updated_at=updated_at,
            updated_by=doc.get("updated_by"),
            created_by=doc.get("created_by"),
        )

    def _doc_to_user_server(self, doc: dict[str, Any]) -> UserMCPServer:
        """Convert MongoDB document to UserMCPServer"""
        created_at = doc.get("created_at")
        updated_at = doc.get("updated_at")

        if created_at and hasattr(created_at, "isoformat"):
            created_at = to_iso(created_at)
        if updated_at and hasattr(updated_at, "isoformat"):
            updated_at = to_iso(updated_at)

        return UserMCPServer(
            name=doc["name"],
            transport=MCPTransport._value2member_map_.get(
                doc.get("transport", "streamable_http"),
                MCPTransport.STREAMABLE_HTTP,
            ),
            enabled=doc.get("enabled", True),
            url=doc.get("url"),
            headers=doc.get("headers"),
            command=doc.get("command"),
            env_keys=doc.get("env_keys"),
            user_id=doc["user_id"],
            is_system=False,
            disabled_tools=_normalize_disabled_tools(doc.get("disabled_tools", [])),
            created_at=created_at,
            updated_at=updated_at,
        )

    def _doc_to_tool_policy(self, doc: dict[str, Any]) -> MCPToolPolicy:
        """Convert MongoDB document to MCPToolPolicy."""
        created_at = doc.get("created_at")
        updated_at = doc.get("updated_at")

        if created_at and hasattr(created_at, "isoformat"):
            created_at = to_iso(created_at)
        if updated_at and hasattr(updated_at, "isoformat"):
            updated_at = to_iso(updated_at)

        return MCPToolPolicy(
            server_name=doc.get("server_name"),
            tool_name=doc.get("tool_name"),
            disabled=doc.get("disabled", False),
            inline_exposure=doc.get("inline_exposure", False),
            allowed_roles=doc.get("allowed_roles", []),
            role_quotas=doc.get("role_quotas", {}),
            created_at=created_at,
            updated_at=updated_at,
            updated_by=doc.get("updated_by"),
        )

    def _doc_to_response(
        self,
        doc: dict[str, Any],
        is_system: bool,
        can_edit: bool,
        hide_sensitive: bool = False,
        already_decrypted: bool = False,
    ) -> MCPServerResponse:
        """Convert MongoDB document to MCPServerResponse with masked sensitive fields.

        Args:
            doc: MongoDB document.
            is_system: Whether this is a system-level server.
            can_edit: Whether the requesting user can edit this server.
            hide_sensitive: If True, omit url/headers/command/env_keys from the
                response entirely (used when non-admins view system servers).
        """
        # Deep copy to avoid modifying original
        doc_copy = copy.deepcopy(doc)

        # 解密敏感字段
        if not already_decrypted:
            doc_copy = decrypt_server_secrets(doc_copy)

        if hide_sensitive:
            # Non-admin viewing a system server: strip all connection details
            for field in ("url", "headers", "command", "env_keys", "env"):
                doc_copy.pop(field, None)
        else:
            # Mask sensitive fields (after decrypt, mask for display)
            doc_copy = self._mask_sensitive_fields(doc_copy)

        # Convert datetime to ISO string if needed
        created_at = doc_copy.get("created_at")
        updated_at = doc_copy.get("updated_at")

        if created_at and hasattr(created_at, "isoformat"):
            created_at = to_iso(created_at)
        if updated_at and hasattr(updated_at, "isoformat"):
            updated_at = to_iso(updated_at)

        return MCPServerResponse(
            name=doc_copy["name"],
            transport=MCPTransport._value2member_map_.get(
                doc_copy.get("transport", "streamable_http"),
                MCPTransport.STREAMABLE_HTTP,
            ),
            enabled=doc_copy.get("enabled", True),
            url=doc_copy.get("url"),
            headers=doc_copy.get("headers"),
            command=doc_copy.get("command"),
            env_keys=doc_copy.get("env_keys"),
            is_system=is_system,
            can_edit=can_edit,
            allowed_roles=doc_copy.get("allowed_roles", []),
            role_quotas=doc_copy.get("role_quotas", {}),
            created_at=created_at,
            updated_at=updated_at,
        )

    def _doc_to_config_dict(
        self,
        doc: dict[str, Any],
        *,
        already_decrypted: bool = False,
    ) -> dict[str, Any]:
        """Convert MongoDB document to config dict format (for langchain-mcp-adapters)"""
        # 先解密敏感字段
        if not already_decrypted:
            doc = decrypt_server_secrets(doc)

        transport = doc.get("transport", "streamable_http")
        result = {"transport": transport}

        if doc.get("url"):
            result["url"] = doc["url"]
        if doc.get("headers"):
            result["headers"] = doc["headers"]
        # Sandbox transport fields
        if doc.get("command"):
            result["command"] = doc["command"]
        if doc.get("env_keys"):
            result["env_keys"] = doc["env_keys"]
        if doc.get("role_quotas"):
            result["role_quotas"] = doc["role_quotas"]

        return result

    def _mask_sensitive_fields(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Remove sensitive fields from document (not shown in edit UI)"""
        # Remove sensitive headers
        headers = doc.get("headers")
        if headers and isinstance(headers, dict):
            keys_to_remove = [
                key
                for key in headers
                if isinstance(key, str) and key.lower() in ["authorization", "x-api-key", "api-key"]
            ]
            for key in keys_to_remove:
                del headers[key]

        # Remove sensitive env variables
        env = doc.get("env")
        if env and isinstance(env, dict):
            keys_to_remove = []
            for key in env:
                if isinstance(key, str):
                    for pattern in SENSITIVE_ENV_PATTERNS:
                        if pattern in key.upper():
                            keys_to_remove.append(key)
                            break
            for key in keys_to_remove:
                del env[key]

        return doc

    async def close(self):
        """Close MongoDB connection (only clears local refs, does not close global client)"""
        self._system_collection = None
        self._user_collection = None
