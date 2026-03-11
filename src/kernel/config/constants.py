"""Configuration constants."""

# Minimum JWT secret key length (32 bytes for HS256)
JWT_SECRET_KEY_MIN_LENGTH = 32

# ============================================
# Settings that require server restart to take effect
# ============================================
RESTART_REQUIRED_SETTINGS = {
    "HOST",
    "PORT",
    "MONGODB_URL",
    "MONGODB_DB",
    "REDIS_URL",
    "REDIS_PASSWORD",
    "JWT_SECRET_KEY",
}

# ============================================
# Sensitive settings - values hidden in API responses
# ============================================
SENSITIVE_SETTINGS = {
    "LLM_API_KEY",
    "ANTHROPIC_API_KEY",
    "SESSION_TITLE_API_KEY",
    "JWT_SECRET_KEY",
    "MONGODB_URL",
    "MONGODB_PASSWORD",
    "REDIS_URL",
    "REDIS_PASSWORD",
    "LANGSMITH_API_KEY",
    "EMBEDDING_API_KEY",
    "RERANK_API_KEY",
    "MILVUS_PASSWORD",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
    "POSTGRES_PASSWORD",
    "OAUTH_GOOGLE_CLIENT_SECRET",
    "OAUTH_GITHUB_CLIENT_SECRET",
    "OAUTH_APPLE_CLIENT_SECRET",
    "TURNSTILE_SECRET_KEY",
    "RESEND_ACCOUNTS",  # JSON array of email accounts
}
