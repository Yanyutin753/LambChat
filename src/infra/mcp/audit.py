"""Credential-safe metadata for MCP authority audit events."""

import json

from src.infra.logging import get_logger
from src.kernel.schemas.user import TokenPayload

logger = get_logger("src.api.routes.mcp")


def audit_mcp(user: TokenPayload, action: str, target: str, *, fields=(), changes=None) -> None:
    logger.info(
        "MCP authority audit %s",
        json.dumps(
            {
                "actor": user.sub,
                "action": action,
                "target": target,
                "fields": sorted(fields),
                "changes": changes or {},
            },
            ensure_ascii=True,
        ),
    )


def policy_changes(data) -> dict:
    return {
        key: value
        for key, value in data.model_dump(mode="json", exclude_unset=True).items()
        if key in {"enabled", "allowed_roles", "role_quotas", "disabled", "inline_exposure"}
    }
