#!/usr/bin/env bash
# py-spy CPU 火焰图助手（宿主机直跑，不进 Pod 文件系统）
#
# 用法:
#   ./pyspy.sh record a [秒数]      # 对 lambchat-a 录制火焰图（默认 60s）
#   ./pyspy.sh record b [秒数]      # 对 lambchat-b
#   ./pyspy.sh record w0|w1 [秒数]  # 对 arq worker 副本
#   ./pyspy.sh dump a               # 立即打印目标进程所有线程调用栈（找挂起/卡死）
#
# 产物: /data/lambchat-monitoring/profiles/<目标>-<时间戳>.svg（浏览器打开）
set -euo pipefail
DIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
NS=${NS:-lambchat}
BIN="$DIR/bin/py-spy"
OUTDIR="$DIR/profiles"
mkdir -p "$OUTDIR"

CMD=${1:?用法: pyspy.sh record|dump <a|b|w0|w1> [秒数]}
TARGET=${2:?缺少目标（a/b/w0/w1）}
DUR=${3:-60}

ensure_binary() {
  if [[ ! -x "$BIN" ]]; then
    echo ">> 下载 py-spy（从 release wheel 中解出二进制）..."
    mkdir -p "$(dirname "$BIN")" /tmp/pyspy-dl
    local VER URL
    VER=$(curl -sf https://api.github.com/repos/benfred/py-spy/releases/latest | grep -oE '"tag_name": "[^"]+"' | cut -d'"' -f4)
    URL="https://github.com/benfred/py-spy/releases/download/${VER}/py_spy-${VER#v}-py2.py3-none-manylinux_2_5_x86_64.manylinux1_x86_64.whl"
    curl -sfL "$URL" -o /tmp/pyspy-dl/py_spy.whl
    PYSPY_BIN_PATH="$BIN" python3 - <<'PY'
import zipfile, os, shutil, stat
z = zipfile.ZipFile("/tmp/pyspy-dl/py_spy.whl")
names = z.namelist()
cand = [n for n in names if n == "py-spy" or n.rstrip("/").split("/")[-1] == "py-spy"]
if not cand:
    raise SystemExit(f"wheel 中未找到 py-spy 可执行文件: {names}")
z.extract(cand[0], "/tmp/pyspy-dl")
dst = os.environ["PYSPY_BIN_PATH"]
shutil.move(os.path.join("/tmp/pyspy-dl", cand[0]), dst)
os.chmod(dst, os.stat(dst).st_mode | stat.S_IEXEC)
PY
    echo ">> py-spy $VER 就绪"
  fi
}

# 通过监听端口反查 hostNetwork 容器进程的宿主机 PID
port_pid() {
  ss -tlnp "sport = :$1" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | head -1
}

# worker 无监听端口：用 Pod 内 PID1 cmdline 在宿主机反查
worker_pid() {
  local idx=$(( ${TARGET#w} )) pod marker
  pod=$(kubectl -n "$NS" get pod -l app=lambchat-worker -o jsonpath="{.items[$idx].metadata.name}")
  marker=$(kubectl -n "$NS" exec "$pod" -- sh -c "tr '\0' ' ' < /proc/1/cmdline" | awk '{print $1, $2}')
  pgrep -f "$marker" | head -1
}

resolve_pid() {
  case "$TARGET" in
    a) port_pid 8011 ;;
    b) port_pid 8012 ;;
    w0|w1) worker_pid ;;
    *) echo "未知目标: $TARGET（支持 a/b/w0/w1）" >&2; return 1 ;;
  esac
}

ensure_binary
PID=$(resolve_pid)
[[ -n "${PID:-}" ]] || { echo ">> 未找到 $TARGET 的宿主机进程"; exit 1; }
echo ">> 目标: $TARGET 宿主机 PID=$PID"

case "$CMD" in
  record)
    TS=$(date +%Y%m%d-%H%M%S)
    echo ">> 录制 ${DUR}s CPU 火焰图（期间保持 ssh 连接）..."
    "$BIN" record -o "$OUTDIR/${TARGET}-${TS}.svg" --format flamegraph --pid "$PID" -d "$DUR" --rate 50 --subprocesses
    echo ">> 完成: $OUTDIR/${TARGET}-${TS}.svg"
    ;;
  dump)
    "$BIN" dump --pid "$PID"
    ;;
  *) echo "未知命令: $CMD"; exit 1 ;;
esac
