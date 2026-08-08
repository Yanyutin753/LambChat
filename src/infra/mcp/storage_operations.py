"""MCP storage combined operations, import/export, promote/demote, and tool discovery."""

import copy
from typing import TYPE_CHECKING, Any, Optional

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.utils.datetime import utc_now_iso
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

if TYPE_CHECKING:
    from src.infra.mcp.storage import MCPStorage


def _server_list_limit() -> int:
    from src.infra.mcp.storage import MCP_SERVER_LIST_LIMIT

    return MCP_SERVER_LIST_LIMIT


def _limit_cursor(cursor: Any, limit: int) -> Any:
    limit_method = getattr(cursor, "limit", None)
    if callable(limit_method):
        return limit_method(limit)
    return cursor


def _can_access_system_server(
    allowed_roles: list[str] | None,
    user_roles: list[str] | None,
    *,
    is_admin: bool = False,
) -> bool:
    """Return whether a user can access a system MCP server."""
    if is_admin:
        return True
    if not allowed_roles:
        return True
    return bool(set(user_roles or []).intersection(allowed_roles))


def _is_legacy_sandbox_server(doc: dict[str, Any] | None) -> bool:
    """Return whether a stored document belongs to the removed Sandbox MCP transport."""
    return bool(doc) and doc.get("transport") == "sandbox"


def _get_effective_config_max_servers() -> int:
    value = getattr(settings, "MCP_EFFECTIVE_CONFIG_MAX_SERVERS", 100)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 100


async def _doc_to_system_server(self: "MCPStorage", doc: dict[str, Any]) -> SystemMCPServer:
    converter = getattr(self, "_doc_to_system_server_async", None)
    if callable(converter):
        return await converter(doc)
    return self._doc_to_system_server(doc)


async def _doc_to_user_server(self: "MCPStorage", doc: dict[str, Any]) -> UserMCPServer:
    converter = getattr(self, "_doc_to_user_server_async", None)
    if callable(converter):
        return await converter(doc)
    return self._doc_to_user_server(doc)


async def _doc_to_config_dict(self: "MCPStorage", doc: dict[str, Any]) -> dict[str, Any]:
    converter = getattr(self, "_doc_to_config_dict_async", None)
    if callable(converter):
        return await converter(doc)
    return self._doc_to_config_dict(doc)


async def _doc_to_response(
    self: "MCPStorage",
    doc: dict[str, Any],
    *,
    is_system: bool,
    can_edit: bool,
    hide_sensitive: bool = False,
) -> MCPServerResponse:
    converter = getattr(self, "_doc_to_response_async", None)
    if callable(converter):
        return await converter(
            doc,
            is_system=is_system,
            can_edit=can_edit,
            hide_sensitive=hide_sensitive,
        )
    return self._doc_to_response(
        doc,
        is_system=is_system,
        can_edit=can_edit,
        hide_sensitive=hide_sensitive,
    )


class StorageOperations:
    """Combined operations, import/export, promote/demote, and tool discovery for MCPStorage.

    These methods are mixed into MCPStorage via inheritance to keep storage.py under 1000 lines.
    All methods operate on the same MongoDB collections as the base class.
    """

    # ==========================================
    # Server Type Conversion (Admin only)
    # ==========================================

    async def promote_to_system_server(  # type: ignore[misc]
        self: "MCPStorage", name: str, user_id: str, admin_user_id: str
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
        if await self.system_server_name_exists(name):
            return None  # Conflict

        # Create system server
        now = utc_now_iso()
        system_collection = self._get_system_collection()
        doc = {
            "name": user_server.name,
            "transport": user_server.transport.value,
            "enabled": user_server.enabled,
            "url": user_server.url,
            "headers": user_server.headers,
            "is_system": True,
            "role_quotas": {},
            "created_at": user_server.created_at or now,
            "updated_at": now,
            "updated_by": admin_user_id,
            "promoted_from_user": user_id,  # Track origin
            "created_by": user_id,  # Original creator
        }
        # 加密敏感字段
        from src.infra.mcp.encryption import encrypt_server_secrets

        doc = await run_blocking_io(encrypt_server_secrets, doc)

        await system_collection.insert_one(doc)

        # Delete the user server (this will invalidate user cache)
        await self.delete_user_server(name, user_id)

        # Invalidate all caches since system server now exists
        await self._invalidate_all_cache()

        return await _doc_to_system_server(self, doc)

    async def demote_to_user_server(  # type: ignore[misc]
        self: "MCPStorage", name: str, target_user_id: str, admin_user_id: str
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
        if await self.user_server_name_exists(name, target_user_id):
            return None  # Conflict

        # Create user server
        now = utc_now_iso()
        user_collection = self._get_user_collection()
        doc = {
            "name": system_server.name,
            "transport": system_server.transport.value,
            "enabled": system_server.enabled,
            "url": system_server.url,
            "headers": system_server.headers,
            "user_id": target_user_id,
            "is_system": False,
            "created_at": system_server.created_at or now,
            "updated_at": now,
        }
        # 加密敏感字段
        from src.infra.mcp.encryption import encrypt_server_secrets

        doc = await run_blocking_io(encrypt_server_secrets, doc)

        await user_collection.insert_one(doc)

        # Delete the system server (this will invalidate all caches)
        await self.delete_system_server(name)

        # Invalidate cache for target user
        await self._invalidate_user_cache(target_user_id)

        return await _doc_to_user_server(self, doc)

    async def get_effective_config(  # type: ignore[misc]
        self: "MCPStorage",
        user_id: str,
        user_roles: list[str] | None = None,
        is_admin: bool = False,
    ) -> dict[str, Any]:
        """
        Get effective MCP configuration for a user.

        Merges system and user configurations, with user preferences taking precedence.
        Only includes servers that are enabled (after applying user preferences).
        System servers with allowed_roles are filtered by the user's roles.
        """
        logger = get_logger(__name__)
        max_servers = _get_effective_config_max_servers()

        # Get user preferences for system servers
        user_preferences = await self._get_user_preferences(user_id)
        logger.info(f"[MCP] User {user_id} preferences: {user_preferences}")

        # Get system servers and apply user preferences
        system_collection = self._get_system_collection()
        system_docs: list[tuple[str, dict[str, Any]]] = []
        system_cursor = _limit_cursor(system_collection.find({}), _server_list_limit())
        async for doc in system_cursor:
            if _is_legacy_sandbox_server(doc):
                continue
            server_name = doc["name"]

            # Role-based access control: filter servers by allowed_roles
            allowed_roles = doc.get("allowed_roles", [])
            if not _can_access_system_server(allowed_roles, user_roles, is_admin=is_admin):
                logger.debug(
                    f"[MCP] User {user_id} (roles: {user_roles}) blocked from server "
                    f"'{server_name}' (allowed: {allowed_roles})"
                )
                continue

            # Check if user has a preference, otherwise use system default
            if server_name in user_preferences:
                is_enabled = user_preferences[server_name]
            else:
                is_enabled = doc.get("enabled", True)

            if is_enabled:
                system_docs.append((server_name, copy.deepcopy(doc)))
                if len(system_docs) >= max_servers:
                    break

        system_policy_loader = getattr(self, "list_tool_policies_for_servers", None)
        system_tool_policies = (
            await system_policy_loader([name for name, _doc in system_docs])
            if callable(system_policy_loader)
            else {}
        )

        system_servers = {}
        for server_name, doc in system_docs:
            config = await _doc_to_config_dict(self, doc)
            tool_policies = system_tool_policies.get(server_name, {})
            if tool_policies:
                config["tool_policies"] = {
                    tool_name: policy.model_dump(mode="json")
                    for tool_name, policy in tool_policies.items()
                }
            system_servers[server_name] = config

        # Get enabled user servers
        user_collection = self._get_user_collection()
        user_servers: dict[str, dict[str, Any]] = {}
        user_cursor = _limit_cursor(
            user_collection.find({"user_id": user_id, "enabled": True}),
            _server_list_limit(),
        )
        async for doc in user_cursor:
            if _is_legacy_sandbox_server(doc):
                continue
            if (
                doc["name"] not in system_servers
                and len(system_servers) + len(user_servers) >= max_servers
            ):
                break
            # Deep copy to avoid modifying the original document
            user_servers[doc["name"]] = await _doc_to_config_dict(self, copy.deepcopy(doc))

        # Merge (user servers override system servers with same name)
        result = {**system_servers, **user_servers}

        logger.info(
            f"[MCP] Effective config for user {user_id}: {list(result.keys())} servers enabled"
        )

        return {"mcpServers": result}

    async def get_visible_servers(  # type: ignore[misc]
        self: "MCPStorage",
        user_id: str,
        is_admin: bool = False,
        user_roles: list[str] | None = None,
        limit: int | None = None,
    ) -> list[MCPServerResponse]:
        """
        Get all MCP servers visible to a user.

        Returns system servers (with user preferences applied) + user's own servers.
        System servers with allowed_roles are filtered — only visible to users with
        a matching role (admins always see everything).
        For system servers, only the creator (created_by) can see sensitive fields
        (url and headers) and edit the server.
        """
        servers = []
        max_servers = max(0, int(limit)) if limit is not None else None

        # Get user preferences for system servers
        user_preferences = await self._get_user_preferences(user_id)

        # Get system servers
        system_collection = self._get_system_collection()
        system_cursor = _limit_cursor(system_collection.find({}), _server_list_limit())
        async for doc in system_cursor:
            if _is_legacy_sandbox_server(doc):
                continue
            # Role-based access control: admins always see everything
            if not is_admin:
                allowed_roles = doc.get("allowed_roles", [])
                if not _can_access_system_server(allowed_roles, user_roles):
                    continue

            # Apply user preference if exists, otherwise use system default
            server_name = doc["name"]
            if server_name in user_preferences:
                doc = copy.deepcopy(doc)
                doc["enabled"] = user_preferences[server_name]
            # Only the creator (created_by) can see sensitive fields
            # Admins can always edit system servers; non-admins cannot
            is_creator = doc.get("created_by", doc.get("updated_by")) == user_id
            can_edit = is_admin or is_creator
            hide_sensitive = not (is_admin or is_creator)
            server = await _doc_to_response(
                self, doc, is_system=True, can_edit=can_edit, hide_sensitive=hide_sensitive
            )
            servers.append(server)
            if max_servers is not None and len(servers) >= max_servers:
                return servers

        # Get user servers
        user_collection = self._get_user_collection()
        user_cursor = _limit_cursor(
            user_collection.find({"user_id": user_id}),
            _server_list_limit(),
        )
        async for doc in user_cursor:
            if _is_legacy_sandbox_server(doc):
                continue
            server = await _doc_to_response(self, doc, is_system=False, can_edit=True)
            servers.append(server)
            if max_servers is not None and len(servers) >= max_servers:
                break

        return servers

    async def can_access_server(  # type: ignore[misc]
        self: "MCPStorage",
        name: str,
        user_id: str,
        user_roles: list[str] | None = None,
        is_admin: bool = False,
    ) -> bool:
        """Return whether a user can access a user-owned or system MCP server."""
        user_collection = self._get_user_collection()
        user_doc = await user_collection.find_one({"name": name, "user_id": user_id})
        if user_doc and not _is_legacy_sandbox_server(user_doc):
            return True

        system_collection = self._get_system_collection()
        system_doc = await system_collection.find_one({"name": name})
        if not system_doc or _is_legacy_sandbox_server(system_doc):
            return False

        return _can_access_system_server(
            system_doc.get("allowed_roles", []),
            user_roles,
            is_admin=is_admin,
        )

    async def toggle_server(  # type: ignore[misc]
        self: "MCPStorage",
        name: str,
        user_id: str,
        user_roles: list[str] | None = None,
        is_admin: bool = False,
    ) -> Optional[MCPServerResponse]:
        """
        Toggle a server's enabled status.

        For user-created servers: toggles the server directly.
        For system servers: toggles the user's preference for that server.
        """
        # First try user-created server
        user_collection = self._get_user_collection()
        user_doc = await user_collection.find_one({"name": name, "user_id": user_id})

        if user_doc and not _is_legacy_sandbox_server(user_doc):
            # Toggle user-created server
            new_enabled = not user_doc.get("enabled", True)
            await user_collection.update_one(
                {"name": name, "user_id": user_id},
                {
                    "$set": {
                        "enabled": new_enabled,
                        "updated_at": utc_now_iso(),
                    }
                },
            )

            # Invalidate cache for this user
            await self._invalidate_user_cache(user_id)

            updated_doc = await user_collection.find_one({"name": name, "user_id": user_id})
            if updated_doc:
                return await _doc_to_response(self, updated_doc, is_system=False, can_edit=True)

        # Check if it's a system server
        system_collection = self._get_system_collection()
        system_doc = await system_collection.find_one({"name": name})

        if system_doc and not _is_legacy_sandbox_server(system_doc):
            if not _can_access_system_server(
                system_doc.get("allowed_roles", []),
                user_roles,
                is_admin=is_admin,
            ):
                return None

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
            is_creator = response_doc.get("created_by", response_doc.get("updated_by")) == user_id
            return await _doc_to_response(self, response_doc, is_system=True, can_edit=is_creator)

        return None

    async def toggle_system_server(self: "MCPStorage", name: str) -> Optional[MCPServerResponse]:  # type: ignore[misc]
        """Toggle a system server's enabled status (admin only)"""
        return await self._toggle_system_server_internal(name)

    async def _toggle_system_server_internal(  # type: ignore[misc]
        self: "MCPStorage", name: str
    ) -> Optional[MCPServerResponse]:
        """Internal method to toggle system server"""
        system_collection = self._get_system_collection()
        system_doc = await system_collection.find_one({"name": name})

        if system_doc and not _is_legacy_sandbox_server(system_doc):
            new_enabled = not system_doc.get("enabled", True)
            await system_collection.update_one(
                {"name": name},
                {
                    "$set": {
                        "enabled": new_enabled,
                        "updated_at": utc_now_iso(),
                    }
                },
            )

            # Invalidate all caches since system server affects all users
            await self._invalidate_all_cache()

            updated_doc = await system_collection.find_one({"name": name})
            if updated_doc:
                return await _doc_to_response(self, updated_doc, is_system=True, can_edit=True)

        return None

    # ==========================================
    # Import/Export
    # ==========================================

    async def import_servers(  # type: ignore[misc]
        self: "MCPStorage",
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
                    allowed_roles=config.get("allowed_roles", []) if is_admin else [],
                    role_quotas=config.get("role_quotas", {}) if is_admin else {},
                )

                # Check if exists
                existing: Optional[SystemMCPServer] | Optional[UserMCPServer] = None
                if is_admin:
                    existing = await self.get_system_server(name)
                    name_reserved = await self.system_server_name_exists(name)
                else:
                    existing = await self.get_user_server(name, user_id)
                    name_reserved = await self.user_server_name_exists(name, user_id)

                if name_reserved and existing is None:
                    skipped += 1
                    continue

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
                                allowed_roles=server.allowed_roles,
                                role_quotas=server.role_quotas,
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

    async def export_user_servers(self: "MCPStorage", user_id: str) -> dict[str, Any]:  # type: ignore[misc]
        """Export user's MCP servers as JSON configuration"""
        user_collection = self._get_user_collection()
        servers = {}

        cursor = _limit_cursor(user_collection.find({"user_id": user_id}), _server_list_limit())
        async for doc in cursor:
            if _is_legacy_sandbox_server(doc):
                continue
            servers[doc["name"]] = await _doc_to_config_dict(self, doc)

        return {"mcpServers": servers}

    async def export_all_servers(self: "MCPStorage") -> dict[str, Any]:  # type: ignore[misc]
        """Export all MCP servers (system only, admin)"""
        system_collection = self._get_system_collection()
        servers = {}

        cursor = _limit_cursor(system_collection.find({}), _server_list_limit())
        async for doc in cursor:
            if _is_legacy_sandbox_server(doc):
                continue
            config = await _doc_to_config_dict(self, doc)
            if doc.get("allowed_roles"):
                config["allowed_roles"] = doc["allowed_roles"]
            if doc.get("role_quotas"):
                config["role_quotas"] = doc["role_quotas"]
            servers[doc["name"]] = config

        return {"mcpServers": servers}
