"""selfupdate：latest release 查询、平台资产匹配、下载替换自体。

不碰真实网络（真实路径由端到端冒烟验证）：httpx.MockTransport 假造
GitHub API 与资产下载端点；替换自体用 tmp_path 里的假 argv[0] 文件真实
走一遍写 .new → 原子换的文件操作。
"""

from __future__ import annotations

import hashlib
import stat

import httpx
import pytest

import lambchat_sandbox
from lambchat_sandbox import selfupdate


def _api_response(tag: str, assets: list[dict]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "tag_name": tag,
            "assets": [
                {
                    "name": a["name"],
                    "browser_download_url": f"https://dl.example/{a['name']}",
                    **({"digest": a["digest"]} if "digest" in a else {}),
                }
                for a in assets
            ],
        },
    )


def _transport(
    *,
    api_response: httpx.Response | None = None,
    api_status: int = 200,
    asset_content: bytes = b"NEW-BINARY",
    asset_status: int = 200,
    log: list[httpx.Request] | None = None,
) -> httpx.MockTransport:
    """假造 releases/latest 与资产下载两端点；记录请求供断言。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if log is not None:
            log.append(request)
        if request.url.path.endswith("/releases/latest"):
            if api_status >= 400:
                return httpx.Response(api_status, json={"message": "Not Found"})
            assert api_response is not None
            return api_response
        if request.url.host == "dl.example":
            if asset_status >= 400:
                return httpx.Response(asset_status, text="boom")
            return httpx.Response(200, content=asset_content)
        return httpx.Response(404, text="unknown")

    return httpx.MockTransport(handler)


_TRIPLE = selfupdate.host_triple()
_ASSET_NAME = f"lambchat-daemon-{_TRIPLE}" + (".exe" if _TRIPLE.endswith("msvc") else "")


@pytest.fixture(autouse=True)
def _fake_argv0(monkeypatch, tmp_path):
    """安全带：把 argv[0] 钉到 tmp 假文件——perform_update 默认替换
    ``Path(sys.argv[0])``，不钉住会让测试把 pytest 自己换掉（真发生过）。"""
    fake = tmp_path / "lambchat-daemon"
    fake.write_bytes(b"OLD-BINARY")
    monkeypatch.setattr(selfupdate.sys, "argv", [str(fake)])
    return fake


# ---------- check_latest ----------


def test_check_latest_finds_newer_platform_asset():
    resp = _api_response(
        "v0.2.0",
        [
            {"name": "lambchat-daemon-aarch64-apple-darwin"},
            {"name": _ASSET_NAME, "digest": "sha256:" + "0" * 64},
        ],
    )
    result = selfupdate.check_latest(
        "Yanyutin753/LambChat", current_version="0.1.0", transport=_transport(api_response=resp)
    )
    assert result == ("0.2.0", f"https://dl.example/{_ASSET_NAME}")


def test_check_latest_without_matching_asset_returns_none():
    """release 存在但无当前平台资产：无更新可用（None），不误报版本。"""
    resp = _api_response("v0.2.0", [{"name": "lambchat-daemon-some-other-triple"}])
    assert (
        selfupdate.check_latest(
            "Yanyutin753/LambChat",
            current_version="0.1.0",
            transport=_transport(api_response=resp),
        )
        is None
    )


def test_check_latest_already_up_to_date_returns_none():
    """release 版本 <= 当前（含相等与更低）：None，不触发下载。"""
    for tag in ("v0.1.0", "0.1.0", "v0.0.9"):
        resp = _api_response(tag, [{"name": _ASSET_NAME}])
        assert (
            selfupdate.check_latest(
                "Yanyutin753/LambChat",
                current_version="0.1.0",
                transport=_transport(api_response=resp),
            )
            is None
        ), tag


def test_check_latest_no_release_at_all_returns_none():
    """仓库还没有任何 release（404）：优雅降级为 None。"""
    assert (
        selfupdate.check_latest(
            "Yanyutin753/LambChat",
            current_version="0.1.0",
            transport=_transport(api_status=404),
        )
        is None
    )


def test_check_latest_sends_github_token_when_present(monkeypatch):
    """GITHUB_TOKEN 存在时携带 Authorization 头（私有/限流场景），缺失不发。"""
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token-1")
    log: list[httpx.Request] = []
    resp = _api_response("v0.2.0", [{"name": _ASSET_NAME}])
    selfupdate.check_latest(
        "Yanyutin753/LambChat",
        current_version="0.1.0",
        transport=_transport(api_response=resp, log=log),
    )
    assert log[0].headers["Authorization"] == "Bearer gh-token-1"


def test_host_triple_matrix():
    """三元组映射：linux 按 machine 分 amd64/arm64，darwin/win32 暂定单架构。"""
    assert (
        selfupdate.host_triple(sys_platform="linux", machine="x86_64") == "x86_64-unknown-linux-gnu"
    )
    assert (
        selfupdate.host_triple(sys_platform="linux", machine="aarch64")
        == "aarch64-unknown-linux-gnu"
    )
    assert selfupdate.host_triple(sys_platform="darwin", machine="arm64") == "aarch64-apple-darwin"
    assert selfupdate.host_triple(sys_platform="win32", machine="AMD64") == "x86_64-pc-windows-msvc"


# ---------- perform_update ----------


def _good_transport(
    content: bytes = b"NEW-BINARY",
    log: list[httpx.Request] | None = None,
    asset_name: str = _ASSET_NAME,
):
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    resp = _api_response("v0.2.0", [{"name": asset_name, "digest": digest}])
    return _transport(api_response=resp, asset_content=content, log=log)


def test_perform_update_replaces_target(tmp_path, _fake_argv0):
    """完整替换链：下载 → sha256 校验 → 写 .new → os.replace 原子换 → chmod +x。

    断言假 argv[0] 内容被新二进制替换、.new 临时名无残留、可执行位在。
    """
    log: list[httpx.Request] = []
    target = _fake_argv0

    message = selfupdate.perform_update(
        "Yanyutin753/LambChat", transport=_good_transport(b"NEW-BINARY", log)
    )

    assert "0.2.0" in message
    assert "重启" in message
    assert target.read_bytes() == b"NEW-BINARY"
    assert not (tmp_path / "lambchat-daemon.new").exists()  # 临时名无残留
    assert stat.S_IMODE(target.stat().st_mode) & stat.S_IXUSR  # chmod +x
    assert len(log) == 2  # releases/latest + 资产下载各一次


def test_perform_update_already_latest_leaves_target(_fake_argv0):
    """已是最新：目标文件原样不动、不发起资产下载。"""
    log: list[httpx.Request] = []
    resp = _api_response("v0.1.0", [{"name": _ASSET_NAME}])  # 与当前同版

    message = selfupdate.perform_update(
        "Yanyutin753/LambChat",
        current_version="0.1.0",
        transport=_transport(api_response=resp, log=log),
    )

    assert "0.1.0" in message
    assert _fake_argv0.read_bytes() == b"OLD-BINARY"
    assert len(log) == 1  # 只查了 release，没有下载


def test_perform_update_download_failure_raises(_fake_argv0):
    """下载失败：check 通过但资产端点 500 → SelfUpdateError，目标保持原样。"""
    resp = _api_response("v0.2.0", [{"name": _ASSET_NAME}])
    with pytest.raises(selfupdate.SelfUpdateError, match="下载"):
        selfupdate.perform_update(
            "Yanyutin753/LambChat", transport=_transport(api_response=resp, asset_status=500)
        )
    assert _fake_argv0.read_bytes() == b"OLD-BINARY"


def test_perform_update_digest_mismatch_raises(tmp_path, _fake_argv0):
    """digest 校验：资产内容与 release 声明的 sha256 不符 → 拒绝替换。"""
    bad_digest = "sha256:" + hashlib.sha256(b"DIFFERENT").hexdigest()
    resp = _api_response("v0.2.0", [{"name": _ASSET_NAME, "digest": bad_digest}])
    with pytest.raises(selfupdate.SelfUpdateError, match="校验"):
        selfupdate.perform_update(
            "Yanyutin753/LambChat", transport=_transport(api_response=resp, asset_content=b"EVIL")
        )
    assert _fake_argv0.read_bytes() == b"OLD-BINARY"
    assert not (tmp_path / "lambchat-daemon.new").exists()  # 失败清理临时文件


def test_perform_update_without_digest_skips_verification(_fake_argv0):
    """资产未声明 digest：跳过校验并注明（不误伤无摘要的早期 release）。"""
    resp = _api_response("v0.2.0", [{"name": _ASSET_NAME}])  # 无 digest 字段

    message = selfupdate.perform_update(
        "Yanyutin753/LambChat", transport=_transport(api_response=resp, asset_content=b"NEW")
    )

    assert _fake_argv0.read_bytes() == b"NEW"
    assert "跳过" in message  # 输出注明未校验


def test_perform_update_windows_rename_order(monkeypatch, tmp_path):
    """Windows 分支（Linux 上模拟）：旧件先改名 .old 再换新件——顺序错了
    会在“运行中的 exe 不能被覆盖”上炸。后验项：真机行为留 CI/人工。"""
    target = tmp_path / "lambchat-daemon.exe"
    target.write_bytes(b"OLD-BINARY")
    monkeypatch.setattr("lambchat_sandbox.platform._sys_platform", "win32")
    win_asset = f"lambchat-daemon-{selfupdate.host_triple()}.exe"  # monkeypatch 后解析

    selfupdate.perform_update(
        "Yanyutin753/LambChat",
        target_path=target,
        transport=_good_transport(b"NEW-BINARY", asset_name=win_asset),
    )

    assert target.read_bytes() == b"NEW-BINARY"
    assert (tmp_path / "lambchat-daemon.exe.old").read_bytes() == b"OLD-BINARY"
    assert not (tmp_path / "lambchat-daemon.exe.new").exists()


# ---------- CLI update 子命令 ----------


def test_cli_update_prints_result(monkeypatch, capsys):
    monkeypatch.setattr(selfupdate, "perform_update", lambda repo: "已是最新（0.1.0），无需更新")
    from lambchat_sandbox.cli import main

    assert main(["update"]) == 0
    assert "已是最新" in capsys.readouterr().out


def test_cli_update_network_error_is_friendly(monkeypatch, capsys):
    """网络失败友好错误：stderr 一行说明 + 退出码 1，不吐 traceback。"""
    monkeypatch.setattr(
        selfupdate,
        "perform_update",
        lambda repo: (_ for _ in ()).throw(httpx.ConnectError("no route")),
    )
    from lambchat_sandbox.cli import main

    assert main(["update"]) == 1
    err = capsys.readouterr().err
    assert "无法连接" in err
    assert "Traceback" not in err


def test_cli_update_accepts_repo_override(monkeypatch, capsys):
    seen: dict[str, str] = {}

    def fake_perform(repo):
        seen["repo"] = repo
        return "已更新到 0.2.0，重启后生效"

    monkeypatch.setattr(selfupdate, "perform_update", fake_perform)
    from lambchat_sandbox.cli import main

    assert main(["update", "--repo", "someone/LambChat-fork"]) == 0
    assert seen["repo"] == "someone/LambChat-fork"


def test_current_version_defaults_to_package_version():
    """未显式传 current_version 时用 lambchat_sandbox.__version__ 兜底。"""
    assert selfupdate._current_version(None) == lambchat_sandbox.__version__
    assert selfupdate._current_version("9.9.9") == "9.9.9"
