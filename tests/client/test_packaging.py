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
    # v2.9.2 层1：macOS 上内嵌 dylib/so 构建期强制 ad-hoc 落印——PyInstaller
    # 默认启发式在 arm64 宿主会跳过部分内嵌二进制签名，未签名 dylib 在
    # arm64 内核 dlopen 即 SIGKILL；None 会让签名随宿主环境漂移
    assert 'codesign_identity="-" if __import__("sys").platform == "darwin" else None' in spec


def test_build_script_resigns_and_verifies_macos_sidecar() -> None:
    script = _source("client/scripts/build-daemon.sh")

    assert 'case "$TRIPLE" in' in script
    assert "*-apple-darwin)" in script
    assert 'codesign --force --sign "-"' in script
    assert "codesign --verify --strict --verbose=2" in script


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
    by_label = {entry["label"]: entry for entry in matrix}
    # M3 下线的 Windows/macOS 条目已恢复；macOS 双架构（M4 裁决的 arm64
    # 单架构在 M5 升级）：两条目都在 macos-14（arm64）上构建——Rust 侧
    # 交叉编译 x86_64，daemon 侧由 build-daemon.sh 走 Rosetta 路径
    assert set(by_label) == {
        "Linux x86_64",
        "Linux ARM64",
        "Windows",
        "macOS Apple Silicon",
        "macOS Intel",
    }
    assert by_label["macOS Apple Silicon"]["runner"] == "macos-14"
    assert by_label["macOS Intel"]["runner"] == "macos-14"
    assert by_label["macOS Apple Silicon"]["target"] == "aarch64-apple-darwin"
    assert by_label["macOS Intel"]["target"] == "x86_64-apple-darwin"
    # dmg 仅首装；app bundle 产出 .app.tar.gz 供 Tauri updater 增量更新
    assert by_label["macOS Apple Silicon"]["bundles"] == "dmg,app"
    assert by_label["macOS Intel"]["bundles"] == "dmg,app"
    assert by_label["Windows"]["bundles"] == "msi"
    # PBS 平台标签与 fetch-pbs.py 的 PLATFORM_TRIPLES 键一致
    assert {entry["pbs_platform"] for entry in matrix} == {
        "linux-x86_64",
        "linux-aarch64",
        "windows-x86_64",
        "macos-arm64",
        "macos-x64",
    }
    # 资产名带架构后缀：双 mac 构建产物不得同名互踩
    assert by_label["macOS Apple Silicon"]["asset_suffix"] == "macOS-Apple-Silicon"
    assert by_label["macOS Intel"]["asset_suffix"] == "macOS-Intel"


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


def test_release_workflow_publishes_assets_immediately_per_platform() -> None:
    """即发即传：各平台 job 构建完成立即上传 Release，不等六端汇总 job。

    汇总 job 退化为兜底（权威重生成 latest.json + 部分失败打捞），
    资产可用性由各 job 自身的发布步骤保证。
    """
    workflow = _release_workflow()

    def job_step_names(job: str) -> list[str]:
        return [step["name"] for step in workflow["jobs"][job]["steps"]]

    # desktop / android / ios 三个构建 job 都有即发即传步骤
    assert "Publish desktop assets to release immediately" in job_step_names("desktop")
    assert "Publish Android assets to release immediately" in job_step_names("android")
    assert "Publish iOS archive to release immediately" in job_step_names("ios")

    def step_run(job: str, name: str) -> str:
        step = next(s for s in workflow["jobs"][job]["steps"] if s["name"] == name)
        return step["run"]

    desktop_run = step_run("desktop", "Publish desktop assets to release immediately")
    # 创建竞态收敛：已存在即跳过 + 退避重试；上传幂等（--clobber）
    assert "gh release view" in desktop_run
    assert "gh release create" in desktop_run
    assert "--clobber" in desktop_run
    assert "--generate-notes" in desktop_run

    # updater 平台（linux x2 + windows + macOS）增量合并 latest.json
    matrix = _desktop_job()["strategy"]["matrix"]["include"]
    by_label = {entry["label"]: entry for entry in matrix}
    assert by_label["Linux x86_64"]["updater_key"] == "linux-x86_64"
    assert by_label["Linux ARM64"]["updater_key"] == "linux-aarch64"
    assert by_label["Windows"]["updater_key"] == "windows-x86_64"
    # macOS updater 走 .app.tar.gz（dmg 不能原地更新）；双架构各有平台键，
    # sig 按 Tauri updater 产物名的 arch 段区分（_aarch64 / _x64）
    assert by_label["macOS Apple Silicon"]["updater_key"] == "darwin-aarch64"
    assert by_label["macOS Apple Silicon"]["updater_sig"] == "*-macOS-Apple-Silicon.app.tar.gz.sig"
    assert by_label["macOS Apple Silicon"]["updater_asset_suffix"] == (
        "macOS-Apple-Silicon.app.tar.gz"
    )
    assert by_label["macOS Intel"]["updater_key"] == "darwin-x86_64"
    assert by_label["macOS Intel"]["updater_sig"] == "*-macOS-Intel.app.tar.gz.sig"
    assert by_label["macOS Intel"]["updater_asset_suffix"] == "macOS-Intel.app.tar.gz"
    merge_step = next(
        s
        for s in _desktop_job()["steps"]
        if s["name"] == "Merge updater platform entry into latest.json"
    )
    assert merge_step["if"] == "matrix.updater_key != ''"
    # node 合并（三平台镜像都有 Node；Windows 无 python3）
    assert "node -e" in merge_step["run"]

    # 汇总 job 保留：权威 latest.json + 兜底重发
    release_job = workflow["jobs"]["release"]
    assert release_job["if"] == "always()"
    release_steps = job_step_names("release")
    assert "Generate latest.json updater manifest" in release_steps
    assert "Publish release" in release_steps


def test_release_workflow_guards_version_drift_and_manifest_version_from_tag() -> None:
    """v2.8.2 事故防线：tauri.conf.json 漂移到 2.8.1 时 latest.json 报 2.8.1，
    桌面端永远检测不到更新。三道闸：打包前 preflight 校验、清单版本一律
    取自 tag、macOS updater 条目纳入权威重生成。
    """
    workflow = _release_workflow()

    # 闸 1：三个构建 job 打包前都有版本一致性校验，失败即中止
    for job in ("desktop", "android", "ios"):
        names = [s["name"] for s in workflow["jobs"][job]["steps"]]
        preflight = next(
            s
            for s in workflow["jobs"][job]["steps"]
            if s["name"] == "Preflight version consistency"
        )
        assert "versionCode" in preflight["run"], job
        assert "MARKETING_VERSION" in preflight["run"], job
        # 服务端版本（/api/version 运行时读 pyproject.toml）同入门禁：
        # 漏 bump 会让网页端展示的版本与客户端发版不同步
        assert "pyproject.toml=$pyproject" in preflight["run"], job
        # daemon 版本（lambchat_sandbox.__version__，自 2.8.6 起随发版统一
        # 递增）：漏 bump 会让 daemon self-update 比版本无变化、永不更新
        assert "daemon __version__=$daemon" in preflight["run"], job

    # 闸 2：增量合并的 manifest.version 取自 tag（不再读 tauri.conf.json）
    merge_step = next(
        s
        for s in _desktop_job()["steps"]
        if s["name"] == "Merge updater platform entry into latest.json"
    )
    assert 'RELEASE_TAG.replace(/^v/, "")' in merge_step["run"]
    # 不再从 tauri.conf.json 读版本（漂移源）
    assert 'readFileSync("frontend/src-tauri/tauri.conf.json")' not in merge_step["run"]

    # 闸 3：权威重生成委托公共生成器（app-release 与手动 publish 工作流
    # 共用），版本取 tag、双 darwin 架构条目齐全的契约随之落在生成器内
    regen = next(
        s
        for s in workflow["jobs"]["release"]["steps"]
        if s["name"] == "Generate latest.json updater manifest"
    )
    assert "scripts/generate_updater_manifest.py" in regen["run"]
    generator = _source("scripts/generate_updater_manifest.py")
    assert 'version = tag.lstrip("v")' in generator
    # 不读 tauri.conf.json 取版本（漂移源）——版本只从 RELEASE_TAG 派生；
    # docstring 提及 updater.endpoints 不算读取
    assert 'os.environ.get("RELEASE_TAG"' in generator
    assert not [
        ln for ln in generator.splitlines() if "tauri.conf" in ln and ("read" in ln or "open" in ln)
    ]
    assert '("darwin-aarch64", "*-macOS-Apple-Silicon.app.tar.gz.sig"' in generator
    assert '("darwin-x86_64", "*-macOS-Intel.app.tar.gz.sig"' in generator
    # 五桌面平台不齐时拒发（exit 2）：缺 darwin-x86_64 不许算发布完成
    assert (
        'REQUIRED_PLATFORMS = ("darwin-aarch64", "darwin-x86_64", "linux-x86_64", "windows-x86_64")'
        in generator
    )


def test_release_workflow_macos_collect_requires_app_tar_gz() -> None:
    """macOS 收集步骤必须上传 .app.tar.gz updater 产物且缺失即失败：
    静默跳过会让 darwin 平台条目被略过、mac 永远收不到更新。双 mac 构建
    产物名一律走 matrix.asset_suffix（带架构后缀），不得共享无后缀的
    ``-macOS.*`` 名（两架构互踩 clobber）。"""
    collect = next(
        s for s in _desktop_job()["steps"] if s["name"] == "Collect macOS desktop artifacts"
    )
    assert "*.app.tar.gz" in collect["run"]
    assert "${{ matrix.asset_suffix }}" in collect["run"]
    assert "LambChat-${RELEASE_TAG}-macOS" not in collect["run"]
    assert "exit 1" in collect["run"]


def test_tauri_bundle_adhoc_signs_macos_app() -> None:
    """v2.8.4 事故：未配 signingIdentity 时 Tauri 跳过 bundle 签名，.app 无
    _CodeSignature/CodeResources 封印，浏览器下载（带隔离标记）后被
    Gatekeeper 判「已损坏，无法打开」。"-" = ad-hoc 签名，是无 Apple 开发者
    证书时开源项目的标准分发做法（公证仍不可用，需 xattr 引导兜底）。"""
    import json

    conf = json.loads(_source("frontend/src-tauri/tauri.conf.json"))
    assert conf["bundle"]["macOS"]["signingIdentity"] == "-"


def test_tauri_bundle_disables_hardened_runtime_for_adhoc_sidecar() -> None:
    """v2.10.0 发版事故防线：Tauri 默认对全部可执行（含 daemon sidecar）落
    hardened runtime 标志，而 runtime 隐含 library validation——PyInstaller
    onefile 运行时解包的内嵌 dylib 是无团队 ID 的 ad-hoc 签名，LV 下 dlopen
    即 SIGKILL（v2.9.2 macOS「daemon 起不来」根因）。ad-hoc 分发不做公证，
    runtime 标志只有害处，必须在打包期关闭；打包后重封 sidecar 补救不可行
    （破坏外层封印，且 updater 归档先于重封生成、包内仍是坏字节）。"""
    import json

    conf = json.loads(_source("frontend/src-tauri/tauri.conf.json"))
    assert conf["bundle"]["macOS"]["hardenedRuntime"] is False


def test_release_workflow_verifies_macos_code_signing() -> None:
    """签名门禁（v2.9.2 层2）：macOS 打包后验证 sidecar 无 runtime 标志
    （打包期由 tauri.conf.json hardenedRuntime: false 保证，出现即打包链
    回归）、bundle 封印与嵌套可执行逐一签名（arm64 内核要求全部可执行代码
    至少 ad-hoc 签名）。只验证不修改——改内嵌二进制会破坏外层封印。"""
    steps = {step["name"]: step for step in _desktop_job()["steps"]}
    verify = steps["Verify macOS code signing (sidecar must have no runtime flag)"]
    assert verify["if"] == "runner.os == 'macOS'"
    # 门禁：CodeDirectory flags 含 runtime (0x10000) 即红
    assert "flags=0x[0-9a-f]*1[0-9a-f]{4}" in verify["run"]
    assert "codesign --verify --deep --strict" in verify["run"]
    assert "_CodeSignature/CodeResources" in verify["run"]


def test_release_workflow_smokes_packaged_daemon_version() -> None:
    """打包产物冒烟门禁（v2.9.0/v2.9.2 事故根治）：在**真实打包产物**上跑
    daemon version 断言——macOS 直接执行 .app 内 sidecar（签名/dylib 击杀
    当场红）、Linux 解包 deb 执行并锁布局、Windows 执行构建产物 sidecar。
    仅 codesign --verify 看不到运行时问题。"""
    steps = {step["name"]: step for step in _desktop_job()["steps"]}
    smoke = steps["Packaged daemon smoke (version assert)"]
    assert '"$bin" version' in smoke["run"]
    assert "${RELEASE_TAG#v}" in smoke["run"]
    # macOS 走 .app 内 sidecar（不是构建目录里的裸 sidecar）
    assert "$app_path/Contents/MacOS/lambchat-daemon" in smoke["run"]
    # Linux 解包 deb 并锁 externalBin 落位（v2.9.0 路径事故锚点）
    assert "dpkg-deb -x" in smoke["run"]
    assert "test -x /tmp/deb-x/usr/bin/lambchat" in smoke["run"]


def test_release_workflow_appends_macos_gatekeeper_note() -> None:
    """Release Notes 固定附 xattr 解法（与下载页 macOS 分区提示同一命令），
    marker 前缀保证重跑幂等。"""
    note = next(
        s
        for s in _release_workflow()["jobs"]["release"]["steps"]
        if s["name"] == "Append macOS Gatekeeper install note"
    )
    assert "xattr -cr /Applications/LambChat.app" in note["run"]
    assert "gh release edit" in note["run"]
    assert "macos-gatekeeper-note" in note["run"]


# ---------------------------------------------------------------------------
# macOS 一键安装脚本：curl 下载无隔离标记 → 解包即用（绕开 Gatekeeper）
# ---------------------------------------------------------------------------


def test_install_script_exists_with_macos_arm64_gate() -> None:
    """install.sh 随前端 public/ 分发（/install.sh），必须带 Darwin 门禁并
    双架构路由：arm64 / x86_64 各取对应稳定名资产（M5 起 Intel 同步支持）。"""
    script = _source("frontend/public/install.sh")

    assert script, "frontend/public/install.sh 不存在"
    assert '(uname -s)" = "Darwin"' in script
    assert "arm64)" in script
    assert "x86_64)" in script
    assert "set -euo pipefail" in script


def test_install_script_downloads_stable_named_release_asset() -> None:
    """脚本从 GitHub「最新 release 稳定名」资产下载（免 API 解析、免限流），
    按架构路由资产名，解包目标 /Applications，并兜底清除隔离标记。"""
    script = _source("frontend/public/install.sh")

    assert "releases/latest/download/" in script
    assert "LambChat-macOS-Apple-Silicon-latest.app.tar.gz" in script
    assert "LambChat-macOS-Intel-latest.app.tar.gz" in script
    assert "tar -xzf" in script
    assert "/Applications" in script or "APP_DIR" in script
    assert "com.apple.quarantine" in script


def test_release_workflow_collects_stable_named_macos_asset() -> None:
    """macOS 收集步骤把 .app.tar.gz 以稳定名额外拷贝一份（双架构各一，
    经 matrix.asset_suffix 插值 → LambChat-macOS-Apple-Silicon-latest /
    LambChat-macOS-Intel-latest）：一键安装脚本按
    releases/latest/download/<稳定名> 直链下载，不解析版本号。"""
    collect = next(
        s for s in _desktop_job()["steps"] if s["name"] == "Collect macOS desktop artifacts"
    )
    assert "LambChat-${{ matrix.asset_suffix }}-latest.app.tar.gz" in collect["run"]


def test_build_script_appends_exe_suffix_on_windows_sidecar() -> None:
    script = _source("client/scripts/build-daemon.sh")

    # Windows triple → .exe 后缀（PyInstaller 产物与 Tauri externalBin 双侧约定）
    assert "*-windows-*)" in script
    assert 'EXE_SUFFIX=".exe"' in script
    assert 'EXE_SUFFIX=""' in script
    assert "lambchat-daemon${EXE_SUFFIX}" in script
    assert "lambchat-daemon-${TRIPLE}${EXE_SUFFIX}" in script


def test_build_script_honors_target_triple_override() -> None:
    """DAEMON_TARGET_TRIPLE 覆盖：CI 在 arm64 宿主上产 x86_64 sidecar 时
    注入（与 Tauri --target 对齐）；缺省仍探测宿主 triple。"""
    script = _source("client/scripts/build-daemon.sh")

    assert "DAEMON_TARGET_TRIPLE" in script
    assert "${DAEMON_TARGET_TRIPLE:-$(detect_host_triple)}" in script


def test_build_script_cross_builds_via_rosetta_on_arm64_mac() -> None:
    """arm64 宿主 × x86_64 目标 = Rosetta 路径：PyInstaller 不支持交叉编译，
    必须整套换 x86_64 工具链（x86_64 uv 静态二进制由 Rosetta 自动接手），
    且用独立 venv 隔离宿主 arm64 环境。"""
    script = _source("client/scripts/build-daemon.sh")

    # Rosetta 存在性保障（GH arm64 runner 预装，本地兜底自装）
    assert "install-rosetta" in script
    # x86_64 uv 静态二进制下载（PATH 前置后 uv run/pyinstaller 全链 x86_64）
    assert "uv-x86_64-apple-darwin.tar.gz" in script
    assert "PATH=" in script
    # uv 托管解释器目录按版本不按架构区分：不隔离会复用宿主 arm64 CPython；
    # 且找不到托管解释器时 uv 回退系统 PATH（runner 预装 arm64 3.12 即被采用），
    # 必须 only-managed + 显式安装双保险（实验首两跑实测）
    assert "UV_PYTHON_INSTALL_DIR" in script
    assert "UV_PYTHON_PREFERENCE=only-managed" in script
    assert "uv python install 3.12" in script
    # 独立 venv：不污染宿主 arm64 .venv（落 client/build/，已 gitignore）
    assert "UV_PROJECT_ENVIRONMENT" in script
    assert "venv-daemon-x86_64" in script
    # 防回归门禁：解释器架构现场断言（工具链退回 arm64 时立即失败）
    assert 'platform.machine() == "x86_64"' in script
    # cryptography ≥50 无 macOS x86_64 wheel（openssl-sys 交叉必败，实验三跑
    # 实测）：daemon 导入面仅 httpx + psutil，跳过安装 + --no-sync 防回拉
    assert "--no-install-package cryptography" in script
    assert "uv run --no-sync pyinstaller" in script


def test_release_workflow_daemon_build_passes_target_triple() -> None:
    """daemon 构建步骤必须把 matrix.target 透传为 DAEMON_TARGET_TRIPLE，
    否则 Intel 条目的 sidecar 仍按宿主（arm64）triple 命名、externalBin 落空。"""
    steps = {step["name"]: step for step in _desktop_job()["steps"]}
    daemon_step = steps["Build sandbox daemon sidecar (PyInstaller)"]
    env = daemon_step.get("env", {})
    assert env.get("DAEMON_TARGET_TRIPLE") == "${{ matrix.target || '' }}"


def test_release_workflow_rustup_target_follows_matrix() -> None:
    """rustup target 步骤必须用 matrix.target（原 aarch64 硬编码会让 Intel
    条目缺 x86_64 编译目标直接失败）。"""
    steps = {step["name"]: step for step in _desktop_job()["steps"]}
    rustup = steps["Add macOS Rust target"]
    assert "rustup target add ${{ matrix.target }}" in rustup["run"]


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
