#!/usr/bin/env bash
# 打包 lambchat_sandbox daemon：PyInstaller onefile → Tauri sidecar 产物。
#
# 产物链：
#   client/pyinstaller.spec（入口 __main__.py，= python -m lambchat_sandbox）
#     → client/dist/lambchat-daemon（单文件二进制；Windows 为 lambchat-daemon.exe）
#     → frontend/src-tauri/binaries/lambchat-daemon-<triple>
#       （Tauri externalBin 约定；Windows 要求 <triple>.exe 后缀）
#
# host triple 探测：优先 rustc -vV 的 host: 行（与 Tauri 打包机一致），
# 无 rustc 时按 uname -m 映射 linux-gnu triple。
#
# 交叉目标（DAEMON_TARGET_TRIPLE 环境变量）：CI 在 arm64 macOS 上产 x86_64
# sidecar 时注入（与 Tauri --target x86_64-apple-darwin 对齐）。PyInstaller
# 不支持交叉编译，走 Rosetta 路径：换 x86_64 静态 uv（arm64 shell 里由
# Rosetta 自动接手）+ 独立 venv，uv run 自动按锁文件同步 x86_64 解释器与依赖。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

detect_host_triple() {
    if command -v rustc >/dev/null 2>&1; then
        host="$(rustc -vV | sed -n 's/^host:[[:space:]]*//p')"
        if [ -n "$host" ]; then
            printf '%s\n' "$host"
            return 0
        fi
    fi
    case "$(uname -m)" in
        x86_64 | amd64) echo "x86_64-unknown-linux-gnu" ;;
        aarch64 | arm64) echo "aarch64-unknown-linux-gnu" ;;
        *)
            echo "无法探测 host triple（rustc 不可用且 uname -m=$(uname -m) 未映射）" >&2
            return 1
            ;;
    esac
}

# arm64 宿主上产 x86_64 daemon（Rosetta 路径）。GitHub arm64 runner 预装
# Rosetta，本地缺失时兜底自装；uv 版本锚定支持 pyproject default-index
# 字段的当前版（与 CI setup-uv latest 对齐），可用 UV_X86_VERSION 覆盖。
setup_rosetta_x86_64_toolchain() {
    if ! /usr/bin/pgrep -q oahd; then
            echo "==> 安装 Rosetta 2..."
            softwareupdate --install-rosetta --agree-to-license
        fi
        local uv_version="${UV_X86_VERSION:-0.12.10}"
    local uv_dir="$REPO_ROOT/client/build/uv-x86_64"
    mkdir -p "$uv_dir"
    if [ ! -x "$uv_dir/uv" ]; then
        echo "==> 下载 x86_64 uv ${uv_version}（Rosetta 下运行，产 x86_64 工具链）..."
        curl -fsSL \
            "https://github.com/astral-sh/uv/releases/download/${uv_version}/uv-x86_64-apple-darwin.tar.gz" \
            | tar -xz -C "$uv_dir" --strip-components=1
    fi
    export PATH="$uv_dir:$PATH"
    # 独立的 uv-managed Python 安装目录 + 只用托管解释器：uv 托管目录按
    # 版本不按架构区分，且找不到托管解释器时会回退系统 PATH（runner 预装
    # arm64 3.12 满足版本要求即被采用，产物静默变 arm64——实验首跑即被
    # 下方 machine() 断言拦截）。only-managed + 显式安装双保险。
    export UV_PYTHON_INSTALL_DIR="$REPO_ROOT/client/build/uv-python-x86_64"
    export UV_PYTHON_PREFERENCE=only-managed
    # 独立 venv：与宿主 arm64 .venv 隔离（uv run 按锁文件自动同步）；
    # 落 client/build/（已 gitignore，纯构建期产物）
    export UV_PROJECT_ENVIRONMENT="$REPO_ROOT/client/build/venv-daemon-x86_64"
    echo "==> Rosetta x86_64 工具链就绪: $(command -v uv) ($(uv --version))"
    # x86_64 uv 按自身架构下载 x86_64 PBS 构建到隔离目录
    uv python install 3.12
    # cryptography ≥50 只发 macOS arm64 wheel（上游放弃 Intel），x86_64 环境
    # 会触发 openssl-sys 交叉编译而失败。daemon 真实依赖仅 httpx + psutil
    # （lambchat_sandbox 导入面 xref），PyInstaller 按导入分析打包、不触及
    # cryptography（纯服务端 pywebpush 传递依赖），跳过安装无副作用。
    uv sync --group dev --no-install-package cryptography
    uv run --no-sync python -c \
        'import platform; assert platform.machine() == "x86_64", platform.machine()'
}

TRIPLE="${DAEMON_TARGET_TRIPLE:-$(detect_host_triple)}"
# Windows 产物带 .exe 后缀：PyInstaller 产出 lambchat-daemon.exe，且 Tauri
# externalBin 在 Windows 上按 <name>-<triple>.exe 解析（CI windows runner 的
# triple 探测走 rustc -vV host → x86_64-pc-windows-msvc）
case "$TRIPLE" in
    *-windows-*) EXE_SUFFIX=".exe" ;;
    *) EXE_SUFFIX="" ;;
esac
DIST_ARTIFACT="$REPO_ROOT/client/dist/lambchat-daemon${EXE_SUFFIX}"
# Tauri sidecar 约定命名：binaries/lambchat-daemon-<triple><suffix>
TARGET="$REPO_ROOT/frontend/src-tauri/binaries/lambchat-daemon-${TRIPLE}${EXE_SUFFIX}"
EXPECTED_VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' \
    "$REPO_ROOT/client/lambchat_sandbox/__init__.py")"

echo "==> daemon target triple: $TRIPLE"
cd "$REPO_ROOT"

# macOS arm64 宿主 × x86_64 目标：换 x86_64 工具链（Rust/Go sidecar 可交叉
# 编译，PyInstaller 不行——这是本脚本的 Rosetta 路径存在的原因）
CROSS_ROSETTA=0
if [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ] \
    && [ "$TRIPLE" = "x86_64-apple-darwin" ]; then
    CROSS_ROSETTA=1
    setup_rosetta_x86_64_toolchain
fi

echo "==> PyInstaller 打包 daemon（onefile）..."
# Rosetta 路径已显式 sync（跳过 cryptography），--no-sync 防止 uv run 的
# 自动同步把该包重新拉回（macOS x86_64 无 wheel 必然失败）
if [ "$CROSS_ROSETTA" = 1 ]; then
    uv run --no-sync pyinstaller client/pyinstaller.spec \
        --distpath client/dist \
        --workpath client/build \
        --noconfirm
else
    uv run pyinstaller client/pyinstaller.spec \
        --distpath client/dist \
        --workpath client/build \
        --noconfirm
fi

if [ ! -x "$DIST_ARTIFACT" ]; then
    echo "打包产物缺失或不可执行: $DIST_ARTIFACT" >&2
    exit 1
fi

mkdir -p "$REPO_ROOT/frontend/src-tauri/binaries"
cp -f "$DIST_ARTIFACT" "$TARGET"
chmod +x "$TARGET"

# PyInstaller 的 onefile 会在启动时把内嵌 dylib 解包到临时目录；macOS
# 必须信任这些嵌套代码。对最终 sidecar 再签一次，覆盖 Rosetta 交叉构建、
# PyInstaller 版本差异和 Tauri 复制过程，避免 libpython3.12.dylib 因未签名
# 被 AMFI 拒绝加载。hardened runtime 仍由 Tauri 配置显式关闭。
case "$TRIPLE" in
    *-apple-darwin)
        if ! command -v codesign >/dev/null 2>&1; then
            echo "macOS sidecar 构建需要 codesign" >&2
            exit 1
        fi
        echo "==> ad-hoc 签名 macOS daemon sidecar..."
        codesign --force --sign "-" --timestamp=none "$TARGET"
        codesign --verify --strict --verbose=2 "$TARGET"
        ;;
esac

echo "==> sidecar 产物: $TARGET"
echo "==> 冒烟验证: version 子命令（onefile 首跑解包需数秒）..."
version="$("$TARGET" version)"
echo "    version -> $version"
if [ "$version" != "$EXPECTED_VERSION" ]; then
    echo "版本输出异常: $version（期望 $EXPECTED_VERSION）" >&2
    exit 1
fi
echo "✅ daemon sidecar 打包完成"
