import tomllib
from pathlib import Path


def test_wheel_includes_top_level_plugin_packages() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    packages = project["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]

    assert packages == ["src", "plugins"]
