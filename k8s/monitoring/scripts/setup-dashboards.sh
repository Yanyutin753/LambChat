#!/usr/bin/env bash
# 下载社区看板并生成 ConfigMap（node/redis）+ 生成自建 LambChat 看板 ConfigMap
set -euo pipefail
DIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
DL="$DIR/downloaded-dashboards"
mkdir -p "$DL"

fetch() { # fetch <dashboard-id> <output-name>
  local id=$1 out=$2
  curl -sfL "https://grafana.com/api/dashboards/$id/revisions/latest/download" -o "$DL/$out" \
    && echo "OK  $id -> $out ($(wc -c < "$DL/$out") bytes)" \
    || { echo "FAIL $id -> $out (skipped)"; rm -f "$DL/$out"; return 0; }
}

fetch 1860 node-exporter-full.json   # Node Exporter Full
fetch 11835 redis.json               # Redis Dashboard for Prometheus Redis Exporter
# 注意：不用 grafana.com 的 mongodb/beyla 看板 —— 25800/19565 实测下载到的是
# 无关看板（Solar PV / DOCSIS Modem）。Mongo 与 Beyla 数据均由自建看板覆盖。

mkcm() { # mkcm <configmap-name> <file>
  local name=$1 file=$2 tmp
  [[ -f "$file" ]] || { echo "skip cm $name (no file)"; return 0; }
  tmp=$(mktemp)
  # 不走 kubectl apply：大看板的 last-applied 注解会超 256KB 限制
  kubectl -n monitoring create configmap "$name" --from-file="$file" \
    --dry-run=client -o yaml > "$tmp"
  kubectl -n monitoring create -f "$tmp" 2>/dev/null || kubectl -n monitoring replace -f "$tmp"
  rm -f "$tmp"
  echo "cm $name created/replaced"
}

mkcm dashboard-lambchat-api "$DIR/manifests/dashboards/lambchat-api.json"
mkcm dashboard-lambchat-mongo "$DIR/manifests/dashboards/lambchat-mongo.json"
mkcm dashboard-node-exporter "$DL/node-exporter-full.json"
mkcm dashboard-redis "$DL/redis.json"
# 清理第一版误装的无关看板
kubectl -n monitoring delete configmap dashboard-mongodb dashboard-beyla --ignore-not-found >/dev/null
