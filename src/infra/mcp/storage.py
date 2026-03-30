"""
MCP server storage using MongoDB

Supports both system-level and user-level MCP server configurations.
"""

import copy
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from src.infra.logging import get_logger
from src.infra.mcp.encryption import (
    decrypt_server_secrets,
    encrypt_server_secrets,
    encrypt_value,
)
from src.infra.storage.mongodb import get_mongo_client
from src.kernel.config import settings
from src.kernel.schemas.mcp import (
    MCPImportRequest,
    MCPServerCreate,
    MCPServerResponse,
    MCPServerUpdate,
    MCPTransport,
    SystemMCPServer,
    UserMCPServer,
)

logger = get_logger(__name__)

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

# Sensitive fields that should be masked in responses
SENSITIVE_FIELDS = [
    "headers.Authorization",
    "headers.X-Api-Key",
    "headers.Api-Key",
]

# Patterns for sensitive env variables
SENSITIVE_ENV_PATTERNS = ["_API_KEY", "_SECRET", "_PASSWORD", "_TOKEN"]


class MCPStorage:
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

    # ==========================================
    # System MCP Servers (Admin)
    # ==========================================

    async def list_system_servers(self) -> list[SystemMCPServer]:
        """List all system MCP servers"""
        collection = self._get_system_collection()
        servers = []
        async for doc in collection.find({}):
            servers.append(self._doc_to_system_server(doc))
        return servers

    async def get_system_server(self, name: str) -> Optional[SystemMCPServer]:
        """Get a system MCP server by name"""
        collection = self._get_system_collection()
        doc = await collection.find_one({"name": name})
        if doc:
            return self._doc_to_system_server(doc)
        return None

    async def create_system_server(
        self, server: MCPServerCreate, admin_user_id: str
    ) -> SystemMCPServer:
        """Create a system MCP server (admin only)"""
        collection = self._get_system_collection()

        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "name": server.name,
            "transport": server.transport.value,
            "enabled": server.enabled,
            "url": server.url,
            "headers": server.headers,
            "command": server.command,
            "env_keys": server.env_keys,
            "is_system": True,
            "created_at": now,
            "updated_at": now,
            "updated_by": admin_user_id,
        }

        # 加密敏感字段
        doc = encrypt_server_secrets(doc)

        await collection.insert_one(doc)

        # Invalidate all caches since system server affects all users
        await self._invalidate_all_cache()

        return self._doc_to_system_server(doc)

    async def update_system_server(
        self, name: str, updates: MCPServerUpdate, admin_user_id: str
    ) -> Optional[SystemMCPServer]:
        """Update a system MCP server (admin only)"""
        collection = self._get_system_collection()

        doc = await collection.find_one({"name": name})
        if not doc:
            return None

        update_data: dict[str, Any] = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
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
                encrypt_value(updates.headers) if updates.headers else updates.headers
            )
        if updates.command is not None:
            update_data["command"] = updates.command
        if updates.env_keys is not None:
            update_data["env_keys"] = updates.env_keys

        await collection.update_one({"name": name}, {"$set": update_data})

        # Invalidate all caches since system server affects all users
        await self._invalidate_all_cache()

        updated_doc = await collection.find_one({"name": name})
        return self._doc_to_system_server(updated_doc) if updated_doc else None

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
        async for doc in collection.find({"user_id": user_id}):
            servers.append(self._doc_to_user_server(doc))
        return servers

    async def get_user_server(self, name: str, user_id: str) -> Optional[UserMCPServer]:
        """Get a user's MCP server by name"""
        collection = self._get_user_collection()
        doc = await collection.find_one({"name": name, "user_id": user_id})
        if doc:
            return self._doc_to_user_server(doc)
        return None

    async def create_user_server(self, server: MCPServerCreate, user_id: str) -> UserMCPServer:
        """Create a user MCP server"""
        collection = self._get_user_collection()

        now = datetime.now(timezone.utc).isoformat()
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
        doc = encrypt_server_secrets(doc)

        await collection.insert_one(doc)

        # Invalidate cache for this user
        await self._invalidate_user_cache(user_id)

        return self._doc_to_user_server(doc)

    async def update_user_server(
        self, name: str, updates: MCPServerUpdate, user_id: str
    ) -> Optional[UserMCPServer]:
        """Update a user MCP server"""
        collection = self._get_user_collection()

        doc = await collection.find_one({"name": name, "user_id": user_id})
        if not doc:
            return None

        update_data: dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}

        if updates.transport is not None:
            update_data["transport"] = updates.transport.value
        if updates.enabled is not None:
            update_data["enabled"] = updates.enabled
        if updates.url is not None:
            update_data["url"] = updates.url
        if updates.headers is not None:
            update_data["headers"] = (
                encrypt_value(updates.headers) if updates.headers else updates.headers
            )
        if updates.command is not None:
            update_data["command"] = updates.command
        if updates.env_keys is not None:
            update_data["env_keys"] = updates.env_keys

        await collection.update_one({"name": name, "user_id": user_id}, {"$set": update_data})

        # Invalidate cache for this user
        await self._invalidate_user_cache(user_id)

        updated_doc = await collection.find_one({"name": name, "user_id": user_id})
        return self._doc_to_user_server(updated_doc) if updated_doc else None

    async def delete_user_server(self, name: str, user_id: str) -> bool:
        """Delete a user MCP server"""
        collection = self._get_user_collection()
        result = await collection.delete_one({"name": name, "user_id": user_id})

        # Invalidate cache for this user
        if result.deleted_count > 0:
            await self._invalidate_user_cache(user_id)

        return result.deleted_count > 0

    # ==========================================
    # Server Type Conversion (Admin only)
    # ==========================================

    async def promote_to_system_server(
        self, name: str, user_id: str, admin_user_id: str
    ) -> Optional[SystemMCPServer]:
        """
        Promote a user server to system server (admin only).

        This moves the server from user collection to system collection.
        Returns the new system server, or None if user server not found.
        """
        # Get the user server
        user_server = await self.get_user_server(name, user_id)
        if not user_server:
            return None

        # Check if system server with same name exists
        existing_system = await self.get_system_server(name)
        if existing_system:
            return None  # Conflict

        # Create system server
        now = datetime.now(timezone.utc).isoformat()
        system_collection = self._get_system_collection()
        doc = {
            "name": user_server.name,
            "transport": user_server.transport.value,
            "enabled": user_server.enabled,
            "url": user_server.url,
            "headers": user_server.headers,
            "command": user_server.command,
            "env_keys": user_server.env_keys,
            "is_system": True,
            "created_at": user_server.created_at or now,
            "updated_at": now,
            "updated_by": admin_user_id,
            "promoted_from_user": user_id,  # Track origin
        }
        # 加密敏感字段
        doc = encrypt_server_secrets(doc)

        await system_collection.insert_one(doc)

        # Delete the user server (this will invalidate user cache)
        await self.delete_user_server(name, user_id)

        # Invalidate all caches since system server now exists
        await self._invalidate_all_cache()

        return self._doc_to_system_server(doc)

    async def demote_to_user_server(
        self, name: str, target_user_id: str, admin_user_id: str
    ) -> Optional[UserMCPServer]:
        """
        Demote a system server to user server (admin only).

        This moves the server from system collection to user collection.
        The server will be owned by target_user_id.
        Returns the new user server, or None if system server not found.
        """
        # Get the system server
        system_server = await self.get_system_server(name)
        if not system_server:
            return None

        # Check if user server with same name exists
        existing_user = await self.get_user_server(name, target_user_id)
        if existing_user:
            return None  # Conflict

        # Create user server
        now = datetime.now(timezone.utc).isoformat()
        user_collection = self._get_user_collection()
        doc = {
            "name": system_server.name,
            "transport": system_server.transport.value,
            "enabled": system_server.enabled,
            "url": system_server.url,
            "headers": system_server.headers,
            "command": system_server.command,
            "env_keys": system_server.env_keys,
            "user_id": target_user_id,
            "is_system": False,
            "created_at": system_server.created_at or now,
            "updated_at": now,
        }
        # 加密敏感字段
        doc = encrypt_server_secrets(doc)

        await user_collection.insert_one(doc)

        # Delete the system server (this will invalidate all caches)
        await self.delete_system_server(name)

        # Invalidate cache for target user
        await self._invalidate_user_cache(target_user_id)

        return self._doc_to_user_server(doc)

    # ==========================================
    # User Preferences (for system servers)
    # ==========================================

    async def _get_user_preferences(self, user_id: str) -> dict[str, bool]:
        """Get user's enabled preferences for system servers"""
        collection = self._get_preferences_collection()
        preferences = {}
        async for doc in collection.find({"user_id": user_id}):
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
                    "updated_at": datetime.now(timezone.utc).isoformat(),
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
        self, server_name: str, user_id: str
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
            if not server:
                return [], f"Server '{server_name}' not found"

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
            for tool in tools:
                # langchain-mcp-adapters may prefix with "server_name:"
                # Strip it so the frontend can construct the qualified name itself
                tool_name = tool.name
                if tool_name.startswith(f"{server_name}:"):
                    tool_name = tool_name[len(server_name) + 1 :]
                tool_info: dict[str, Any] = {
                    "name": tool_name,
                    "description": getattr(tool, "description", ""),
                    "parameters": [],
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
                        for param_name, param_info in properties.items():
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
        return result

    async def get_tool_preferences(self, user_id: str) -> dict[str, bool]:
        """
        Get user's tool-level preferences.

        Returns a dict mapping fully qualified tool name (server_name:tool_name or tool_name)
        to enabled status. Only disabled tools are stored, so missing keys mean enabled.
        """
        collection = self._get_tool_preferences_collection()
        preferences: dict[str, bool] = {}
        async for doc in collection.find({"user_id": user_id}):
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
                    "updated_at": datetime.now(timezone.utc).isoformat(),
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

    # ==========================================
    # Combined Operations (for runtime)
    # ==========================================

    async def get_sandbox_servers(self, user_id: str) -> list[dict[str, Any]]:
        """Get all enabled sandbox-transport MCP servers for a user (system + user).

        Used during sandbox rebuild to re-register mcporter configs.
        Returns list of config dicts with name, command, env_keys.
        """
        servers = []

        # System sandbox servers
        system_collection = self._get_system_collection()
        async for doc in system_collection.find({"transport": "sandbox", "enabled": True}):
            servers.append(
                {
                    "name": doc.get("name", ""),
                    "command": doc.get("command", ""),
                    "env_keys": doc.get("env_keys", []),
                }
            )

        # User sandbox servers
        user_collection = self._get_user_collection()
        async for doc in user_collection.find(
            {"user_id": user_id, "transport": "sandbox", "enabled": True}
        ):
            servers.append(
                {
                    "name": doc.get("name", ""),
                    "command": doc.get("command", ""),
                    "env_keys": doc.get("env_keys", []),
                }
            )

        return servers

    async def get_effective_config(self, user_id: str) -> dict[str, Any]:
        """
        Get effective MCP configuration for a user.

        Merges system and user configurations, with user preferences taking precedence.
        Only includes servers that are enabled (after applying user preferences).
        """
        logger = get_logger(__name__)

        # Get user preferences for system servers
        user_preferences = await self._get_user_preferences(user_id)
        logger.info(f"[MCP] User {user_id} preferences: {user_preferences}")

        # Get system servers and apply user preferences
        system_collection = self._get_system_collection()
        system_servers = {}
        async for doc in system_collection.find({}):
            server_name = doc["name"]
            # Check if user has a preference, otherwise use system default
            if server_name in user_preferences:
                is_enabled = user_preferences[server_name]
            else:
                is_enabled = doc.get("enabled", True)

            if is_enabled:
                # Deep copy to avoid modifying the original document
                system_servers[server_name] = self._doc_to_config_dict(copy.deepcopy(doc))

        # Get enabled user servers
        user_collection = self._get_user_collection()
        user_servers = {}
        async for doc in user_collection.find({"user_id": user_id, "enabled": True}):
            # Deep copy to avoid modifying the original document
            user_servers[doc["name"]] = self._doc_to_config_dict(copy.deepcopy(doc))

        # Merge (user servers override system servers with same name)
        result = {**system_servers, **user_servers}

        logger.info(
            f"[MCP] Effective config for user {user_id}: {list(result.keys())} servers enabled"
        )

        return {"mcpServers": result}

    async def get_visible_servers(
        self,
        user_id: str,
        is_admin: bool = False,  # noqa: ARG002
    ) -> list[MCPServerResponse]:
        """
        Get all MCP servers visible to a user.

        Returns system servers (with user preferences applied) + user's own servers.
        Masks sensitive fields in responses.
        """
        servers = []

        # Get user preferences for system servers
        user_preferences = await self._get_user_preferences(user_id)

        # Get system servers
        system_collection = self._get_system_collection()
        async for doc in system_collection.find({}):
            # Apply user preference if exists, otherwise use system default
            server_name = doc["name"]
            if server_name in user_preferences:
                doc = copy.deepcopy(doc)
                doc["enabled"] = user_preferences[server_name]
            server = self._doc_to_response(doc, is_system=True, can_edit=True)
            servers.append(server)

        # Get user servers
        user_collection = self._get_user_collection()
        async for doc in user_collection.find({"user_id": user_id}):
            server = self._doc_to_response(doc, is_system=False, can_edit=True)
            servers.append(server)

        return servers

    async def toggle_server(self, name: str, user_id: str) -> Optional[MCPServerResponse]:
        """
        Toggle a server's enabled status.

        For user-created servers: toggles the server directly.
        For system servers: toggles the user's preference for that server.
        """
        # First try user-created server
        user_collection = self._get_user_collection()
        user_doc = await user_collection.find_one({"name": name, "user_id": user_id})

        if user_doc:
            # Toggle user-created server
            new_enabled = not user_doc.get("enabled", True)
            await user_collection.update_one(
                {"name": name, "user_id": user_id},
                {
                    "$set": {
                        "enabled": new_enabled,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )

            # Invalidate cache for this user
            await self._invalidate_user_cache(user_id)

            updated_doc = await user_collection.find_one({"name": name, "user_id": user_id})
            if updated_doc:
                return self._doc_to_response(updated_doc, is_system=False, can_edit=True)

        # Check if it's a system server
        system_collection = self._get_system_collection()
        system_doc = await system_collection.find_one({"name": name})

        if system_doc:
            # For system servers, toggle user's preference
            # Get current user preference or system default
            preferences = await self._get_user_preferences(user_id)
            current_enabled = preferences.get(name, system_doc.get("enabled", True))
            new_enabled = not current_enabled

            # Save user preference (this will invalidate user cache)
            await self._set_user_preference(name, user_id, new_enabled)

            # Return updated server response with user's preference applied
            response_doc = copy.deepcopy(system_doc)
            response_doc["enabled"] = new_enabled
            return self._doc_to_response(response_doc, is_system=True, can_edit=True)

        return None

    async def toggle_system_server(self, name: str) -> Optional[MCPServerResponse]:
        """Toggle a system server's enabled status (admin only)"""
        return await self._toggle_system_server_internal(name)

    async def _toggle_system_server_internal(self, name: str) -> Optional[MCPServerResponse]:
        """Internal method to toggle system server"""
        system_collection = self._get_system_collection()
        system_doc = await system_collection.find_one({"name": name})

        if system_doc:
            new_enabled = not system_doc.get("enabled", True)
            await system_collection.update_one(
                {"name": name},
                {
                    "$set": {
                        "enabled": new_enabled,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )

            # Invalidate all caches since system server affects all users
            await self._invalidate_all_cache()

            updated_doc = await system_collection.find_one({"name": name})
            if updated_doc:
                return self._doc_to_response(updated_doc, is_system=True, can_edit=True)

        return None

    # ==========================================
    # Import/Export
    # ==========================================

    async def import_servers(
        self,
        import_data: MCPImportRequest,
        user_id: str,
        is_admin: bool = False,
    ) -> tuple[int, int, list[str]]:
        """
        Import MCP servers from JSON configuration.

        Returns (imported_count, skipped_count, errors).
        """
        imported = 0
        skipped = 0
        errors = []

        for name, config in import_data.get_servers().items():
            try:
                # Auto-detect transport if not specified (studio format compatibility)
                transport_str = config.get("transport")
                if not transport_str:
                    if config.get("url"):
                        transport_str = "streamable_http"
                    else:
                        transport_str = "sse"
                try:
                    transport = MCPTransport(transport_str)
                except ValueError:
                    errors.append(f"Invalid transport '{transport_str}' for server '{name}'")
                    continue

                # Create server object
                server = MCPServerCreate(
                    name=name,
                    transport=transport,
                    enabled=config.get("enabled", True),
                    url=config.get("url"),
                    headers=config.get("headers"),
                    command=config.get("command"),
                    env_keys=config.get("env_keys"),
                )

                # Check if exists
                existing: Optional[SystemMCPServer] | Optional[UserMCPServer] = None
                if is_admin:
                    existing = await self.get_system_server(name)
                else:
                    existing = await self.get_user_server(name, user_id)

                if existing and not import_data.overwrite:
                    skipped += 1
                    continue

                # Create or update
                if is_admin:
                    if existing:
                        await self.update_system_server(
                            name,
                            MCPServerUpdate(
                                transport=transport,
                                enabled=server.enabled,
                                url=server.url,
                                headers=server.headers,
                                command=server.command,
                                env_keys=server.env_keys,
                            ),
                            user_id,
                        )
                    else:
                        await self.create_system_server(server, user_id)
                else:
                    if existing:
                        await self.update_user_server(
                            name,
                            MCPServerUpdate(
                                transport=transport,
                                enabled=server.enabled,
                                url=server.url,
                                headers=server.headers,
                                command=server.command,
                                env_keys=server.env_keys,
                            ),
                            user_id,
                        )
                    else:
                        await self.create_user_server(server, user_id)

                imported += 1

            except Exception as e:
                errors.append(f"Error importing '{name}': {str(e)}")

        # Cache invalidation is handled by create/update methods
        # But if admin import, we should invalidate all caches at the end
        if is_admin and imported > 0:
            await self._invalidate_all_cache()

        return imported, skipped, errors

    async def export_user_servers(self, user_id: str) -> dict[str, Any]:
        """Export user's MCP servers as JSON configuration"""
        user_collection = self._get_user_collection()
        servers = {}

        async for doc in user_collection.find({"user_id": user_id}):
            servers[doc["name"]] = self._doc_to_config_dict(doc)

        return {"mcpServers": servers}

    async def export_all_servers(self) -> dict[str, Any]:
        """Export all MCP servers (system only, admin)"""
        system_collection = self._get_system_collection()
        servers = {}

        async for doc in system_collection.find({}):
            servers[doc["name"]] = self._doc_to_config_dict(doc)

        return {"mcpServers": servers}

    # ==========================================
    # Document Conversion
    # ==========================================

    def _doc_to_system_server(self, doc: dict[str, Any]) -> SystemMCPServer:
        """Convert MongoDB document to SystemMCPServer"""
        created_at = doc.get("created_at")
        updated_at = doc.get("updated_at")

        if created_at and hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat()
        if updated_at and hasattr(updated_at, "isoformat"):
            updated_at = updated_at.isoformat()

        # 解密敏感字段
        doc = decrypt_server_secrets(doc)

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
            created_at=created_at,
            updated_at=updated_at,
            updated_by=doc.get("updated_by"),
        )

    def _doc_to_user_server(self, doc: dict[str, Any]) -> UserMCPServer:
        """Convert MongoDB document to UserMCPServer"""
        created_at = doc.get("created_at")
        updated_at = doc.get("updated_at")

        if created_at and hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat()
        if updated_at and hasattr(updated_at, "isoformat"):
            updated_at = updated_at.isoformat()

        # 解密敏感字段
        doc = decrypt_server_secrets(doc)

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
            created_at=created_at,
            updated_at=updated_at,
        )

    def _doc_to_response(
        self, doc: dict[str, Any], is_system: bool, can_edit: bool
    ) -> MCPServerResponse:
        """Convert MongoDB document to MCPServerResponse with masked sensitive fields"""
        # Deep copy to avoid modifying original
        doc_copy = copy.deepcopy(doc)

        # 解密敏感字段
        doc_copy = decrypt_server_secrets(doc_copy)

        # Mask sensitive fields (after decrypt, mask for display)
        doc_copy = self._mask_sensitive_fields(doc_copy)

        # Convert datetime to ISO string if needed
        created_at = doc_copy.get("created_at")
        updated_at = doc_copy.get("updated_at")

        if created_at and hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat()
        if updated_at and hasattr(updated_at, "isoformat"):
            updated_at = updated_at.isoformat()

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
            created_at=created_at,
            updated_at=updated_at,
        )

    def _doc_to_config_dict(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Convert MongoDB document to config dict format (for langchain-mcp-adapters)"""
        # 先解密敏感字段
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
