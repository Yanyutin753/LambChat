#!/usr/bin/env bash
# 打包 lambchat_sandbox daemon：PyInstaller onefile → Tauri sidecar 产物。
#
# 产物链：
#   client/pyinstaller.spec（入口 __main__.py，= python -m lambchat_sandbox）
#     → client/dist/lambchat-daemon（单文件二进制）
#     → frontend/src-tauri/binaries/lambchat-daemon-<host-triple>（Tauri externalBin 约定）
#
# host triple 探测：优先 rustc -vV 的 host: 行（与 Tauri 打包机一致），
# 无 rustc 时按 uname -m 映射 linux-gnu triple。
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

TRIPLE="$(detect_host_triple)"
DIST_ARTIFACT="$REPO_ROOT/client/dist/lambchat-daemon"
# Tauri sidecar 约定命名：binaries/lambchat-daemon-<triple>
TARGET="$REPO_ROOT/frontend/src-tauri/binaries/lambchat-daemon-$TRIPLE"
EXPECTED_VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' \
    "$REPO_ROOT/client/lambchat_sandbox/__init__.py")"

echo "==> host triple: $TRIPLE"
cd "$REPO_ROOT"

echo "==> PyInstaller 打包 daemon（onefile）..."
uv run pyinstaller client/pyinstaller.spec \
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

echo "==> sidecar 产物: $TARGET"
echo "==> 冒烟验证: version 子命令（onefile 首跑解包需数秒）..."
version="$("$TARGET" version)"
echo "    version -> $version"
if [ "$version" != "$EXPECTED_VERSION" ]; then
    echo "版本输出异常: $version（期望 $EXPECTED_VERSION）" >&2
    exit 1
fi
echo "✅ daemon sidecar 打包完成"
