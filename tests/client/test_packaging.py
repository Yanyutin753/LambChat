"""daemon 打包管线结构测试：纯文件断言（前端 ``*Source.test.ts`` 思路的 pytest 版）。

不执行真实打包，只锁定打包管线的结构契约：
- ``client/pyinstaller.spec`` 必须以 ``client/lambchat_sandbox/__main__.py`` 为入口
  （与 ``python -m lambchat_sandbox`` 等价）、onefile、产物名 ``lambchat-daemon``；
- ``client/scripts/build-daemon.sh`` 必须探测 host triple（rustc 优先、uname -m 映射兜底）
  并把产物落位到 Tauri sidecar 约定路径；
- Makefile 必须暴露 ``client-build-daemon`` 目标驱动该脚本。
"""

from pathlib import Path


def _source(path: str) -> str:
    """读文件原文；文件缺失时返回空串，让断言（而非收集错误）暴露缺失。"""
    p = Path(path)
    return p.read_text(encoding="utf-8") if p.exists() else ""


def test_spec_bundles_daemon_entry_as_onefile_named_lambchat_daemon() -> None:
    spec = _source("client/pyinstaller.spec")

    # 入口与 python -m lambchat_sandbox 等价
    assert "client/lambchat_sandbox/__main__.py" in spec
    # 产物名与控制台形态（sidecar 是无 GUI 的常驻进程）
    assert 'name="lambchat-daemon"' in spec
    assert "console=True" in spec
    # onefile 判据：EXE 吸收 binaries/datas，且没有 COLLECT（onedir 才有）
    assert "a.binaries" in spec
    assert "a.datas" in spec
    assert "COLLECT(" not in spec
    # 瘦身契约：排除 httpx[cli]/anyio 可选依赖链（rich→pygments→PIL→numpy、
    # click、zstandard、uvloop 等，均为条件导入，daemon 运行路径用不到）
    for heavy in ("numpy", "PIL", "rich", "pygments", "click", "zstandard", "uvloop", "yaml"):
        assert f'"{heavy}"' in spec, f"spec excludes 应包含 {heavy}"


def test_build_script_detects_host_triple_and_targets_sidecar_path() -> None:
    script = _source("client/scripts/build-daemon.sh")

    # triple 探测：rustc 优先，无 rustc 时 uname -m 映射到 linux-gnu triple
    assert "rustc -vV" in script
    assert "uname -m" in script
    assert "x86_64-unknown-linux-gnu" in script
    assert "aarch64-unknown-linux-gnu" in script
    # 打包调用链与产物落点
    assert "client/pyinstaller.spec" in script
    assert "--distpath client/dist" in script
    assert "frontend/src-tauri/binaries/lambchat-daemon-" in script


def test_makefile_exposes_client_build_daemon_target() -> None:
    makefile = _source("Makefile")

    assert "\nclient-build-daemon:" in makefile
    assert "client/scripts/build-daemon.sh" in makefile


# ---------------------------------------------------------------------------
# 内嵌 PBS 运行时（M4 T4）：fetch 脚本 / Tauri resources / 忽略产物
# ---------------------------------------------------------------------------


def test_tauri_bundle_resources_include_python_runtime() -> None:
    import json

    conf = json.loads(_source("frontend/src-tauri/tauri.conf.json"))
    resources = conf.get("bundle", {}).get("resources", [])
    # fetch-pbs.py 产出的 resources/python/<platform>/python.tar.gz 随包分发
    assert any("resources/python" in str(r) for r in resources), resources


def test_makefile_exposes_client_fetch_pbs_target() -> None:
    makefile = _source("Makefile")

    assert "\nclient-fetch-pbs:" in makefile
    assert "client/scripts/fetch-pbs.py" in makefile


def test_gitignore_excludes_pbs_resource_artifacts() -> None:
    gi = _source(".gitignore")

    # tar.gz 产物不入库（构建期 fetch-pbs.py 现场下载，tag 锁定保可复现）
    assert "frontend/src-tauri/resources/python/" in gi


def test_cargo_lock_is_committed_for_reproducible_shell_builds() -> None:
    """Cargo.lock 入库（M4 T8）：壳（lambchat crate）的可复现构建依赖锁文件，
    .gitignore 不得再忽略它，且文件必须真实存在于工作树。"""
    gi = _source(".gitignore")
    assert "frontend/src-tauri/Cargo.lock" not in gi, "Cargo.lock 不应被 .gitignore 忽略"
    assert Path("frontend/src-tauri/Cargo.lock").exists(), "Cargo.lock 必须入库"


# ---------------------------------------------------------------------------
# app-release.yml 三平台矩阵（M4 T9）：win/mac 恢复 + daemon/PBS 步全平台
# ---------------------------------------------------------------------------


def _release_workflow() -> dict:
    import yaml

    data = yaml.safe_load(_source(".github/workflows/app-release.yml"))
    assert isinstance(data, dict), "app-release.yml must parse as a mapping"
    return data


def _desktop_job() -> dict:
    return _release_workflow()["jobs"]["desktop"]


def test_release_workflow_matrix_covers_three_platforms() -> None:
    matrix = _desktop_job()["strategy"]["matrix"]["include"]
    by_runner = {entry["runner"]: entry for entry in matrix}
    # M3 下线的 Windows/macOS 条目已恢复；macOS M4 裁决为 arm64 单架构
    assert set(by_runner) == {
        "ubuntu-latest",
        "ubuntu-24.04-arm",
        "windows-2022",
        "macos-14",
    }
    assert by_runner["macos-14"]["target"] == "aarch64-apple-darwin"
    assert by_runner["macos-14"]["bundles"] == "dmg"
    assert by_runner["windows-2022"]["bundles"] == "msi"
    # PBS 平台标签与 fetch-pbs.py 的 PLATFORM_TRIPLES 键一致
    assert {entry["pbs_platform"] for entry in matrix} == {
        "linux-x86_64",
        "linux-aarch64",
        "windows-x86_64",
        "macos-arm64",
    }


def test_release_workflow_daemon_steps_run_on_all_platforms() -> None:
    steps = {step["name"]: step for step in _desktop_job()["steps"]}
    daemon_step = steps["Build sandbox daemon sidecar (PyInstaller)"]
    # 三平台同链路：不得再用 runner.os == 'Linux' 收窄
    assert "if" not in daemon_step
    assert "if" not in steps["Install uv"]
    assert "if" not in steps["Set up Python"]
    # bash shell（Windows 默认 pwsh 跑不了 bash 脚本）；直调脚本而非 make
    # （windows-2022 镜像不预装 GNU make）
    assert daemon_step.get("shell") == "bash"
    assert "client/scripts/build-daemon.sh" in daemon_step["run"]
    assert "make client-build-daemon" not in daemon_step["run"]


def test_release_workflow_fetches_pbs_per_platform_after_daemon() -> None:
    steps = _desktop_job()["steps"]
    names = [step["name"] for step in steps]
    daemon_idx = names.index("Build sandbox daemon sidecar (PyInstaller)")
    pbs_idx = names.index("Fetch embedded Python runtime (PBS)")
    # PBS 归档在 daemon 步之后、tauri 打包之前按当前平台拉取
    assert pbs_idx > daemon_idx
    assert pbs_idx < names.index("Build desktop package with Tauri")
    pbs_step = steps[pbs_idx]
    assert "if" not in pbs_step  # 全平台
    assert "client/scripts/fetch-pbs.py" in pbs_step["run"]
    assert "${{ matrix.pbs_platform }}" in pbs_step["run"]


def test_build_script_appends_exe_suffix_on_windows_sidecar() -> None:
    script = _source("client/scripts/build-daemon.sh")

    # Windows triple → .exe 后缀（PyInstaller 产物与 Tauri externalBin 双侧约定）
    assert "*-windows-*)" in script
    assert 'EXE_SUFFIX=".exe"' in script
    assert 'EXE_SUFFIX=""' in script
    assert "lambchat-daemon${EXE_SUFFIX}" in script
    assert "lambchat-daemon-${TRIPLE}${EXE_SUFFIX}" in script


def test_release_workflow_collect_steps_publish_daemon_sidecar_assets() -> None:
    """三个 Collect 步骤必须把 daemon sidecar 二进制拷入 release-assets/。

    selfupdate 按 ``lambchat-daemon-<triple>`` 前缀匹配 release 资产
    （client/lambchat_sandbox/selfupdate.py 的 ASSET_PREFIX + host_triple），
    所以拷贝必须保留 triple 原名（Windows 加 ``.exe``），不得套 RELEASE_TAG
    重命名——否则 CLI 自更新永远找不到平台资产（M4 final-review F1）。
    """
    steps = {step["name"]: step for step in _desktop_job()["steps"]}
    expected = {
        "Collect Linux desktop artifacts": "lambchat-daemon-*",
        "Collect Windows desktop artifacts": "lambchat-daemon-*.exe",
        "Collect macOS desktop artifacts": "lambchat-daemon-*",
    }
    for name, pattern in expected.items():
        run = steps[name]["run"]
        assert f"frontend/src-tauri/binaries/{pattern}" in run, (
            f"{name} 应把 {pattern} 拷入 release-assets/"
        )
        for line in run.splitlines():
            if "lambchat-daemon" in line and "binaries/" in line:
                assert "release-assets" in line, (
                    f"{name}: daemon sidecar 拷贝必须落入 release-assets/"
                )
                assert "RELEASE_TAG" not in line, (
                    f"{name}: daemon 资产名保留 triple 原名，不得重命名"
                )
