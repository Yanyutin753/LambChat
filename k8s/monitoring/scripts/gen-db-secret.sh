#!/usr/bin/env bash
# 从 LambChat 的 secret + Deployment 环境变量派生监测组件所需凭据，
# 写入 monitoring 命名空间的 monitoring-db-auth / monitoring-grafana-auth。
#
# 兼容两种配置形态：
#   - 仓库示例 k8s/lambchat-secret.yaml.example：secret lambchat-secrets，
#     键名小写连字符（mongodb-username），MONGODB_URL 等写在 Deployment env
#   - 线上形态：secret lambchat-env，键名大写下划线（MONGODB_USERNAME），
#     MONGODB_URL 等也在 secret 里
# 全程在服务器本地完成，不向 stdout 输出任何凭据值。
#
# 可用环境变量覆盖：
#   LAMBCHAT_NS       LambChat 命名空间（默认 lambchat）
#   LAMBCHAT_SECRET   凭据 secret 名（默认自动探测 lambchat-env / lambchat-secrets）
set -euo pipefail

DIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
LAMBCHAT_NS=${LAMBCHAT_NS:-lambchat}
LAMBCHAT_SECRET=${LAMBCHAT_SECRET:-}

if [[ -z "$LAMBCHAT_SECRET" ]]; then
  for s in lambchat-env lambchat-secrets; do
    if kubectl -n "$LAMBCHAT_NS" get secret "$s" >/dev/null 2>&1; then
      LAMBCHAT_SECRET=$s
      break
    fi
  done
fi
[[ -n "$LAMBCHAT_SECRET" ]] || { echo "!! 未找到 LambChat 凭据 secret（lambchat-env / lambchat-secrets）"; exit 1; }
echo ">> 凭据来源: $LAMBCHAT_NS/$LAMBCHAT_SECRET"

PYTMP=$(mktemp /tmp/gen-db-secret.XXXXXX.py)
trap 'rm -f "$PYTMP"' EXIT
cat > "$PYTMP" <<'PY'
import base64, json, subprocess, sys, urllib.parse

lambchat_ns, secret_name = sys.argv[1], sys.argv[2]

def kubectl_json(*args):
    return json.loads(subprocess.run(["kubectl", "-n", lambchat_ns, *args],
                                     capture_output=True, check=True).stdout)

d = {k: base64.b64decode(v).decode()
     for k, v in kubectl_json("get", "secret", secret_name, "-o", "json")["data"].items()}

def pick(*names):
    for n in names:
        if d.get(n):
            return d[n]
    return ""

def deploy_env(name):
    # 扫描命名空间内所有 Deployment 的明文 env（仓库清单形态）
    for dep in kubectl_json("get", "deploy", "-o", "json")["items"]:
        for c in dep["spec"]["template"]["spec"].get("containers", []):
            for ev in c.get("env", []):
                if ev.get("name") == name and ev.get("value"):
                    return ev["value"]
    return ""

mongo_url = deploy_env("MONGODB_URL") or pick("MONGODB_URL")
redis_url = deploy_env("REDIS_URL") or pick("REDIS_URL")
auth = deploy_env("MONGODB_AUTH_SOURCE") or pick("MONGODB_AUTH_SOURCE") or "admin"

u = urllib.parse.urlparse(mongo_url or "mongodb://127.0.0.1:27017")
host, port = u.hostname or "127.0.0.1", u.port or 27017
user = urllib.parse.quote(pick("MONGODB_USERNAME", "mongodb-username"), safe="")
pwd = urllib.parse.quote(pick("MONGODB_PASSWORD", "mongodb-password"), safe="")
extra_q = {}
if u.query:
    for kv in u.query.split("&"):
        if "=" in kv:
            k, v = kv.split("=", 1)
            if k != "authSource":
                extra_q[k] = v
extra_q["authSource"] = auth
mongo_uri = f"mongodb://{user}:{pwd}@{host}:{port}/?{urllib.parse.urlencode(extra_q)}"

ru = urllib.parse.urlparse(redis_url or "redis://127.0.0.1:6379")
redis_addr = f"{ru.hostname or '127.0.0.1'}:{ru.port or 6379}"

items = [{
    "apiVersion": "v1", "kind": "Secret",
    "metadata": {"name": "monitoring-db-auth", "namespace": "monitoring"},
    "type": "Opaque",
    "stringData": {
        "MONGODB_URI": mongo_uri,
        "REDIS_ADDR": redis_addr,
        "REDIS_PASSWORD": pick("REDIS_PASSWORD", "redis-password"),
    },
}]
json.dump({"apiVersion": "v1", "kind": "List", "items": items}, sys.stdout)
PY

python3 "$PYTMP" "$LAMBCHAT_NS" "$LAMBCHAT_SECRET" | kubectl apply -f -

# Grafana admin 密码只在首次生成：Grafana 落库后 GF_SECURITY_ADMIN_PASSWORD 不再生效，
# 重复生成反而造成「secret/密码文件」与真实密码漂移。
if ! kubectl -n monitoring get secret monitoring-grafana-auth >/dev/null 2>&1; then
  PW=$(python3 -c "import secrets, string; print(''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16)))")
  kubectl -n monitoring create secret generic monitoring-grafana-auth \
    --from-literal=admin-password="$PW" >/dev/null
  umask 077
  echo "$PW" > "$DIR/.grafana-admin-password"
  echo ">> 已生成 monitoring-grafana-auth（密码记于 $DIR/.grafana-admin-password，勿提交）"
else
  echo ">> monitoring-grafana-auth 已存在，保留原密码"
fi
echo ">> 凭据 secret 就绪（值不回显）"
