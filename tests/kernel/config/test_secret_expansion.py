from src.kernel.config.base import Settings
from src.kernel.config.constants import MCP_ENCRYPTION_SALT_MIN_LENGTH
from src.kernel.config.definitions import SETTING_DEFINITIONS
from src.kernel.config.utils import expand_encryption_salt


def test_expand_encryption_salt_is_deterministic_for_short_values() -> None:
    first = expand_encryption_salt("shared-salt")
    second = expand_encryption_salt("shared-salt")

    assert first == second
    assert len(first) >= MCP_ENCRYPTION_SALT_MIN_LENGTH
    assert first != "shared-salt"


def test_expand_encryption_salt_leaves_long_values_unchanged() -> None:
    salt = "a" * MCP_ENCRYPTION_SALT_MIN_LENGTH

    assert expand_encryption_salt(salt) == salt


def test_settings_marks_generated_secrets() -> None:
    settings = Settings(
        _env_file=None,
        JWT_SECRET_KEY="",
        MCP_ENCRYPTION_SALT=None,
    )

    assert settings._jwt_secret_key_generated is True
    assert settings._mcp_encryption_salt_generated is True


def test_settings_does_not_mark_explicit_secrets_as_generated() -> None:
    settings = Settings(
        _env_file=None,
        JWT_SECRET_KEY="stable-jwt-secret-that-is-long-enough",
        MCP_ENCRYPTION_SALT="stable-mcp-salt",
    )

    assert settings._jwt_secret_key_generated is False
    assert settings._mcp_encryption_salt_generated is False


def test_default_agent_setting_points_to_registered_agent_id() -> None:
    settings = Settings(_env_file=None)

    assert settings.DEFAULT_AGENT == "search"
    assert SETTING_DEFINITIONS["DEFAULT_AGENT"]["default"] == "search"
