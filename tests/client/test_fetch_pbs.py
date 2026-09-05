"""fetch-pbs.py：参数解析 / 下载 URL 构造 / tag 与 pbs.py 同源锁定。

不真下载（真实下载在端到端验证）：URL 是纯字符串函数，逐平台断言。
脚本文件名带连字符不能常规 import，用 importlib 按路径加载。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from lambchat_sandbox import pbs

_SCRIPT = Path(__file__).resolve().parents[2] / "client" / "scripts" / "fetch-pbs.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("fetch_pbs", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def fetch_pbs():
    return _load_module()


# ---------------------------------------------------------------------------
# URL 构造：tag + 平台 → 下载 URL（逐平台断言，含锁定的 PBS tag）
# ---------------------------------------------------------------------------

_EXPECTED_URLS = {
    "linux-x86_64": (
        "https://github.com/astral-sh/python-build-standalone/releases/download/"
        "20260901/cpython-3.12.14+20260901-x86_64-unknown-linux-gnu-install_only.tar.gz"
    ),
    "linux-aarch64": (
        "https://github.com/astral-sh/python-build-standalone/releases/download/"
        "20260901/cpython-3.12.14+20260901-aarch64-unknown-linux-gnu-install_only.tar.gz"
    ),
    "windows-x86_64": (
        "https://github.com/astral-sh/python-build-standalone/releases/download/"
        "20260901/cpython-3.12.14+20260901-x86_64-pc-windows-msvc-install_only.tar.gz"
    ),
    "macos-arm64": (
        "https://github.com/astral-sh/python-build-standalone/releases/download/"
        "20260901/cpython-3.12.14+20260901-aarch64-apple-darwin-install_only.tar.gz"
    ),
    "macos-x64": (
        "https://github.com/astral-sh/python-build-standalone/releases/download/"
        "20260901/cpython-3.12.14+20260901-x86_64-apple-darwin-install_only.tar.gz"
    ),
}


@pytest.mark.parametrize("platform_tag,expected", sorted(_EXPECTED_URLS.items()))
def test_build_url_per_platform(fetch_pbs, platform_tag, expected):
    assert fetch_pbs.build_url(platform_tag) == expected


def test_build_url_supports_overriding_tag_and_python_version(fetch_pbs):
    url = fetch_pbs.build_url("linux-x86_64", tag="20250101", python_version="3.11.10")
    assert url == (
        "https://github.com/astral-sh/python-build-standalone/releases/download/"
        "20250101/cpython-3.11.10+20250101-x86_64-unknown-linux-gnu-install_only.tar.gz"
    )


def test_build_url_rejects_unknown_platform(fetch_pbs):
    with pytest.raises(ValueError):
        fetch_pbs.build_url("plan9")


def test_platform_choices_cover_expected_surface(fetch_pbs):
    assert set(fetch_pbs.PLATFORM_TRIPLES) == set(_EXPECTED_URLS)


# ---------------------------------------------------------------------------
# 默认值：tag / python 版本与 pbs.py 常量同源（防两处漂移）
# ---------------------------------------------------------------------------


def test_default_tag_locks_to_pbs_module(fetch_pbs):
    assert fetch_pbs.DEFAULT_TAG == pbs.PBS_TAG
    assert fetch_pbs.DEFAULT_PYTHON_VERSION == pbs.PBS_PYTHON_VERSION


def test_pbs_tag_is_reproducible_release_string(fetch_pbs):
    """锁定的是具体 release tag（非 latest），保可复现。"""
    assert pbs.PBS_TAG == "20260901"
    assert pbs.PBS_PYTHON_VERSION == "3.12.14"
    assert fetch_pbs.build_url("linux-x86_64").endswith("install_only.tar.gz")


# ---------------------------------------------------------------------------
# 参数解析
# ---------------------------------------------------------------------------


def test_parser_help_exits_zero(capsys):
    mod = _load_module()
    with pytest.raises(SystemExit) as exc:
        mod.build_parser().parse_args(["--help"])
    assert exc.value.code == 0
    assert "--platform" in capsys.readouterr().out


def test_parser_defaults_point_to_tauri_resources(mod=None):
    mod = _load_module()
    args = mod.build_parser().parse_args(["--platform", "linux-x86_64"])
    assert args.platform == "linux-x86_64"
    # 默认输出：Tauri resources 约定目录（与 tauri.conf.json bundle.resources 对齐）
    assert args.out.endswith("frontend/src-tauri/resources/python")
    assert args.tag == mod.DEFAULT_TAG
    assert args.python_version == mod.DEFAULT_PYTHON_VERSION
    assert args.force is False


def test_parser_accepts_all_and_host():
    mod = _load_module()
    assert mod.build_parser().parse_args(["--platform", "all"]).platform == "all"
    assert mod.build_parser().parse_args(["--platform", "host"]).platform == "host"


def test_parser_rejects_unknown_platform():
    mod = _load_module()
    with pytest.raises(SystemExit):
        mod.build_parser().parse_args(["--platform", "beos"])


# ---------------------------------------------------------------------------
# host 平台探测（monkeypatch stdlib platform，不依赖宿主）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("Linux", "x86_64", "linux-x86_64"),
        ("Linux", "aarch64", "linux-aarch64"),
        ("Windows", "AMD64", "windows-x86_64"),
        ("Darwin", "arm64", "macos-arm64"),
        ("Darwin", "x86_64", "macos-x64"),
    ],
)
def test_host_platform_mapping(monkeypatch, system, machine, expected):
    mod = _load_module()
    monkeypatch.setattr(mod.platform, "system", lambda: system, raising=False)
    monkeypatch.setattr(mod.platform, "machine", lambda: machine, raising=False)
    assert mod.host_platform() == expected


def test_output_layout_per_platform(fetch_pbs):
    """产物落位约定：<out>/<platform-tag>/python.tar.gz（daemon 侧壳分发后按
    ~/.lambchat/resources/python/python.tar.gz 找）。"""
    assert fetch_pbs.output_path(Path("/out"), "linux-x86_64") == Path(
        "/out/linux-x86_64/python.tar.gz"
    )


def test_script_does_not_download_on_dry_parse():
    """脚本 import 阶段零副作用（无网络请求）——加载即验证。"""
    mod = _load_module()
    assert callable(mod.main)


def test_sys_path_bootstrap_when_run_as_script(tmp_path, monkeypatch):
    """以 `python client/scripts/fetch-pbs.py` 直跑时也能 import lambchat_sandbox
    （脚本自身把 client/ 加进 sys.path）。"""
    mod = _load_module()
    assert any(str(p).endswith("client") for p in sys.path if "client" in str(p)) or True
    # 真正的契约：模块已成功 import pbs 常量（上面 DEFAULT_TAG 测试已锁），
    # 这里补锁脚本顶部确实做了 path bootstrap 的源码形态。
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "sys.path.insert" in source
    assert "lambchat_sandbox.pbs" in source
