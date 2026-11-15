"""Code-owned feature guides, separate from the editable user skill store."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BuiltinFeatureSkill:
    id: str
    directory: Path
    required_tools: frozenset[str]
    required_capabilities: frozenset[str] = frozenset()
    platform_files: tuple[tuple[str, str], ...] = ()
    unknown_platform_guide: str = ""


BUILTIN_FEATURE_SKILLS = (
    BuiltinFeatureSkill(
        id="computer-use",
        directory=Path(__file__).parent / "computer_use",
        required_tools=frozenset({"computer_use"}),
        required_capabilities=frozenset({"local_computer"}),
        platform_files=(("win32", "windows.md"), ("darwin", "macos.md"), ("linux", "linux.md")),
        unknown_platform_guide="The platform is unknown. Read status and capabilities before choosing platform-specific actions.",
    ),
)
