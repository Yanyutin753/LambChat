#!/usr/bin/env bash
set -euo pipefail
DIR=$(cd -- "$(dirname -- "$0")" && pwd)
export KUBECTL="${KUBECTL:-k3s kubectl}"
exec python3 "$DIR/update.py" "$@"
