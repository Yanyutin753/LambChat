"""Configuration constants."""

# Minimum JWT secret key length (32 bytes for HS256)
JWT_SECRET_KEY_MIN_LENGTH = 32

# Minimum MCP encryption salt length (16 bytes for KDF security)
MCP_ENCRYPTION_SALT_MIN_LENGTH = 16

# ============================================
# Settings that require server restart to take effect
# ============================================
RESTART_REQUIRED_SETTINGS = {
    "HOST",
    "PORT",
    "CHECKPOINT_BACKEND",
    "CHECKPOINT_PG_HOST",
    "CHECKPOINT_PG_PORT",
    "CHECKPOINT_PG_USER",
    "CHECKPOINT_PG_PASSWORD",
    "CHECKPOINT_PG_DB",
    "CHECKPOINT_PG_POOL_MIN_SIZE",
    "CHECKPOINT_PG_POOL_MAX_SIZE",
    "CHECKPOINT_MONGO_POOL_MIN_SIZE",
    "CHECKPOINT_MONGO_POOL_MAX_SIZE",
    "MONGODB_URL",
    "MONGODB_DB",
    "REDIS_URL",
    "REDIS_PASSWORD",
    "JWT_SECRET_KEY",
}


def _build_sensitive_settings() -> set[str]:
    """Build SENSITIVE_SETTINGS from definitions where is_sensitive=True."""
    from src.kernel.config.definitions import SETTING_DEFINITIONS

    return {k for k, v in SETTING_DEFINITIONS.items() if v.get("is_sensitive", False)}


SENSITIVE_SETTINGS = _build_sensitive_settings()
