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
    "MONGODB_POOL_MIN_SIZE",
    "MONGODB_POOL_MAX_SIZE",
    "REDIS_URL",
    "REDIS_PASSWORD",
    "JWT_SECRET_KEY",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "S3_ENABLED",
    "S3_PROVIDER",
    "S3_ENDPOINT_URL",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
    "S3_REGION",
    "S3_BUCKET_NAME",
    "S3_CUSTOM_DOMAIN",
    "S3_PATH_STYLE",
    "S3_PUBLIC_BUCKET",
}


def _build_sensitive_settings() -> set[str]:
    """Build SENSITIVE_SETTINGS from definitions where is_sensitive=True."""
    from src.kernel.config.definitions import SETTING_DEFINITIONS

    return {k for k, v in SETTING_DEFINITIONS.items() if v.get("is_sensitive", False)}


SENSITIVE_SETTINGS = _build_sensitive_settings()
