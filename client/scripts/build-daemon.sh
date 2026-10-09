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
# DAEMON_TARGET_TRIPLE must match the native build host; CI uses one host per architecture.
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

# PyInstaller and its native cryptography dependency must use the target architecture.
if [ "$TRIPLE" != "$(detect_host_triple)" ]; then
    echo "daemon requires a native $TRIPLE build host; cross-architecture packaging is unsupported" >&2
    exit 1
fi

echo "==> PyInstaller 打包 daemon（onefile）..."
if [ "$(uname -s)" = "Darwin" ]; then
    export OPENSSL_DIR="$(brew --prefix openssl@3)"
    export OPENSSL_STATIC=1
fi
uv sync --group dev --group cua
uv run --no-sync pyinstaller client/pyinstaller.spec \
    --distpath client/dist \
    --workpath client/build \
    --noconfirm

if [ ! -x "$DIST_ARTIFACT" ]; then
    echo "打包产物缺失或不可执行: $DIST_ARTIFACT" >&2
    exit 1
fi

mkdir -p "$REPO_ROOT/frontend/src-tauri/binaries"
cp -f "$DIST_ARTIFACT" "$TARGET"
chmod +x "$TARGET"

# PyInstaller 的 onefile 会在启动时把内嵌 dylib 解包到临时目录；macOS
# 必须信任这些嵌套代码。对最终 sidecar 再签一次，覆盖原生构建、
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
