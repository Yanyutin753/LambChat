from pathlib import Path

from src.kernel.extensions.agent_team_service import (
    get_agent_team_directory,
    register_agent_team_directory,
)


def test_agent_team_directory_registration_can_be_replaced_and_cleared() -> None:
    original = get_agent_team_directory()
    replacement = object()
    try:
        register_agent_team_directory(replacement)  # type: ignore[arg-type]
        assert get_agent_team_directory() is replacement
        register_agent_team_directory(None)
        assert get_agent_team_directory() is None
    finally:
        register_agent_team_directory(original)


def test_core_does_not_import_agent_team_implementation() -> None:
    direct_import = "from plugins.system.agent_team"
    offenders = [
        path
        for path in Path("src").rglob("*.py")
        if direct_import in path.read_text(encoding="utf-8")
    ]

    assert offenders == []
