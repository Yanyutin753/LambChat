#!/usr/bin/env bash
# LambChat 性能监测栈一键部署（单机 k3s / monitoring 命名空间）
# 零代码侵入：不改 LambChat 任何镜像与配置。
set -euo pipefail
DIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"

echo "== 1. 命名空间 =="
kubectl apply -f "$DIR/manifests/00-namespace.yaml"

echo "== 2. 派生凭据 secret =="
bash "$DIR/scripts/gen-db-secret.sh"
bash "$DIR/scripts/setup-dashboards.sh"
kubectl apply -f "$DIR/manifests/10-prometheus.yaml"
kubectl apply -f "$DIR/manifests/20-grafana.yaml"
kubectl apply -f "$DIR/manifests/30-node-exporter.yaml"
kubectl apply -f "$DIR/manifests/40-db-exporters.yaml"
kubectl apply -f "$DIR/manifests/41-postgres-exporter.yaml"
kubectl apply -f "$DIR/manifests/50-beyla.yaml"

echo "== 3. 等待 Pod 就绪 =="
kubectl -n monitoring wait --for=condition=ready pod -l app=prometheus --timeout=300s
kubectl -n monitoring wait --for=condition=ready pod -l app=grafana --timeout=300s
kubectl -n monitoring wait --for=condition=ready pod -l app=node-exporter --timeout=300s
kubectl -n monitoring wait --for=condition=ready pod -l app=mongodb-exporter --timeout=300s
kubectl -n monitoring wait --for=condition=ready pod -l app=redis-exporter --timeout=300s
kubectl -n monitoring wait --for=condition=ready pod -l app=postgres-exporter --timeout=300s
kubectl -n monitoring wait --for=condition=ready pod -l app=beyla --timeout=300s

echo "== 完成 =="
kubectl -n monitoring get pods -o wide
