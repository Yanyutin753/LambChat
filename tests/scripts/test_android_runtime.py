"""Runtime archive paths must never write outside the installation directory."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "android_runtime", Path(__file__).parents[2] / "scripts/prepare_android_runtime.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a/../../escape", "a\\b", ""])
def test_archive_path_rejects_escape(name):
    with pytest.raises(ValueError):
        module.archive_path(name)


def test_archive_path_accepts_rootfs_member():
    assert module.archive_path("./usr/bin/python3") == "usr/bin/python3"
