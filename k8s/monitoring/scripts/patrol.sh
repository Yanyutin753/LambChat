#!/usr/bin/env bash
# LambChat 生产一键巡检：慢查询 / DB 健康 / 后端日志 / Redis / API 指标 /
# 监控栈自检 / pub-sub 通道隔离，可选 --pyspy 采 CPU 热点。
#
# 用法:
#   ./patrol.sh                 # 巡检最近 60 分钟
#   ./patrol.sh 240             # 巡检最近 240 分钟
#   ./patrol.sh --pyspy         # 追加 py-spy 热点采样（worker+api 各 15s）
# 退出码: 0=全部干净, 1=有需关注项（可接 cron / 告警）
#
# 可用环境变量覆盖（容器名等因部署而异）:
#   MONGO_CONTAINER / REDIS_CONTAINER / WINDOW_MIN
set -uo pipefail
DIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
WINDOW_MIN=${WINDOW_MIN:-60}
MONGO_CONTAINER=${MONGO_CONTAINER:-1Panel-mongodb-4iZV}
REDIS_CONTAINER=${REDIS_CONTAINER:-1Panel-redis-JWjW}
PG_CONTAINER=${PG_CONTAINER:-1Panel-postgresql-8Oi4}
BIN="$DIR/bin/py-spy"

if [[ "${1:-}" == "--pyspy" ]]; then WITH_PYSPY=1; shift; else WITH_PYSPY=0; fi
[[ "${1:-}" =~ ^[0-9]+$ ]] && WINDOW_MIN=$1

ATTENTION=()
flag() { ATTENTION+=("$1"); echo "  ⚠️  $1"; }
section() { echo; echo "════════ $* ════════"; }
mongo_exec() { docker exec "$MONGO_CONTAINER" mongosh "$(mongo_uri)" --quiet --eval "$1" 2>&1 | grep -v Warning; }
mongo_uri() { kubectl -n monitoring get secret monitoring-db-auth -o jsonpath='{.data.MONGODB_URI}' | base64 -d; }
prom() { curl -s --max-time 10 "127.0.0.1:9090/api/v1/query" --data-urlencode "query=$1"; }

echo "LambChat 巡检 @ $(date '+%F %T')  窗口=${WINDOW_MIN}min"

# ── 1. Mongo 慢查询 ─────────────────────────────────────────────
section "1. Mongo 慢查询（>${WINDOW_MIN}min, >100ms）"
{ docker logs --since "${WINDOW_MIN}m" "$MONGO_CONTAINER" 2>&1 | grep "Slow query" || true; } | python3 -c "
import json, sys
from collections import Counter
c, scan = Counter(), Counter()
for line in sys.stdin:
    try: a = json.loads(line[line.index('{'):])['attr']
    except Exception: continue
    cmd, op = a.get('command', {}), a.get('type')
    if 'find' in cmd: shape = 'find ' + json.dumps(cmd.get('filter', {}))[:40]
    elif 'aggregate' in cmd: shape = 'aggregate ' + str(cmd.get('pipeline', [])[:1])[:40]
    elif op == 'update': shape = 'update ' + json.dumps(cmd.get('q', {}))[:40]
    else: shape = ' '.join(list(cmd.keys())[:3])
    c[(a.get('ns'), shape)] += 1
    if 'COLLSCAN' in (a.get('planSummary') or ''): scan[(a.get('ns'), shape)] += 1
if not c: print('  ✅ 无慢查询')
for (ns, shape), n in c.most_common(): print(f'  {n}x {ns} | {shape}')
import os
sys.exit(1 if scan else 0)
" || flag "存在 COLLSCAN 慢查询（见上）"

# ── 2. Mongo 内部健康 + 僵尸 trace ──────────────────────────────
section "2. Mongo 健康 / 僵尸 trace / error trace"
mongo_exec '
const s = db.getSiblingDB("admin").serverStatus();
print("  queue:", JSON.stringify(s.globalLock.currentQueue), " active:", JSON.stringify(s.globalLock.activeClients), " conn:", s.connections.current);
const t = db.getSiblingDB("agent_state").traces;
print("  running traces:", t.countDocuments({status:"running"}), " 其中超1h:", t.countDocuments({status:"running", updated_at:{$lt:new Date(Date.now()-3600e3)}}));
print("  error traces 24h:", t.countDocuments({status:"error", started_at:{$gte:new Date(Date.now()-86400e3)}}));
'
ZOMBIE=$(mongo_exec 'print(db.getSiblingDB("agent_state").traces.countDocuments({status:"running", updated_at:{$lt:new Date(Date.now()-3600e3)}}))' | tail -1 | tr -d '[:space:]')
[[ "${ZOMBIE:-0}" != "0" ]] && flag "僵尸 running trace ${ZOMBIE} 条（>1h 无更新）"

# ── 3. 后端 ERROR/WARNING 分布 ──────────────────────────────────
section "3. 后端日志 ERROR/WARNING 分布（${WINDOW_MIN}min）"
for d in lambchat-a lambchat-b lambchat-worker; do
  echo "-- $d:"
  kubectl -n lambchat logs deploy/"$d" --since="${WINDOW_MIN}m" 2>/dev/null \
    | grep -oE "\[(ERROR|WARNING)\][^,]{0,70}" | sort | uniq -c | sort -rn | head -3 | sed 's/^/     /'
  ERRN=$(kubectl -n lambchat logs deploy/"$d" --since="${WINDOW_MIN}m" 2>/dev/null | grep -c "\[ERROR\]" || true)
  echo "     ERROR 合计: ${ERRN:-0}"
  [[ "${ERRN:-0}" -gt 20 ]] && flag "$d ERROR ${ERRN} 条（>20，需人工过目）"
done

# ── 4. Redis ────────────────────────────────────────────────────
section "4. Redis"
PW=$(kubectl -n lambchat get secret lambchat-env -o jsonpath='{.data.REDIS_PASSWORD}' | base64 -d)
rc() { docker exec "$REDIS_CONTAINER" redis-cli --no-auth-warning -a "$PW" "$@" 2>/dev/null; }
echo "  slowlog: $(rc SLOWLOG LEN) 条 | blocked: $(rc INFO clients | grep -oP 'blocked_clients:\K\d+')"
rc INFO memory | grep -E "^(used_memory_human|maxmemory_human|mem_fragmentation_ratio)" | sed 's/^/  /'
[[ "$(rc SLOWLOG LEN)" != "0" ]] && flag "Redis 慢日志非零"

# ── 5. API 指标快照（Prometheus/Beyla）──────────────────────────
section "5. API 指标（30m 窗口）"
prom 'topk(5, sum by (http_route) (rate(http_server_request_duration_seconds_count[30m])))' \
  | python3 -c "import json,sys; [print(f\"  {float(r['value'][1]):.3f}/s  {r['metric'].get('http_route')}\") for r in json.load(sys.stdin)['data']['result']]" 2>/dev/null
echo -n "  5xx(30m): "
prom 'sum(rate(http_server_request_duration_seconds_count{http_response_status_code=~"5.."}[30m]))' \
  | python3 -c "import json,sys; r=json.load(sys.stdin)['data']['result']; v=float(r[0]['value'][1]) if r else 0; print(f'{v:.4f}/s'); sys.exit(1 if v>0 else 0)" 2>/dev/null \
  || flag "存在 5xx"
echo -n "  非流式路由 p95: "
prom 'histogram_quantile(0.95, sum by (le) (rate(http_server_request_duration_seconds_bucket{http_route!~".*stream.*",http_route!="/api/{channel_type}/{instance_id}"}[30m])))' \
  | python3 -c "import json,sys; r=json.load(sys.stdin)['data']['result']; print(f'{float(r[0][\"value\"][1])*1000:.0f}ms' if r else '无数据')" 2>/dev/null

# ── 6. 监控栈自身 ───────────────────────────────────────────────
section "6. 监控栈健康"
kubectl -n monitoring get pods --no-headers 2>/dev/null | awk '{print "  "$1, $3, $4" restarts"}'
DOWN=$(kubectl -n monitoring get pods --no-headers 2>/dev/null | awk '$3!="Running"' | wc -l)
[[ "$DOWN" != "0" ]] && flag "监测栈 ${DOWN} 个 Pod 异常"
DOWN_TARGETS=$(prom 'up' | python3 -c "import json,sys; print(sum(1 for r in json.load(sys.stdin)['data']['result'] if r['value'][1]!='1'))" 2>/dev/null)
[[ "${DOWN_TARGETS:-0}" != "0" ]] && flag "Prometheus ${DOWN_TARGETS} 个 target down"
echo "  targets: $(prom 'up' | python3 -c "import json,sys; print(sum(1 for r in json.load(sys.stdin)['data']['result'] if r['value'][1]=='1'), 'up')" 2>/dev/null)"

# ── 7. pub/sub 通道隔离 ─────────────────────────────────────────
section "7. pub/sub 通道隔离"
CHANNELS=$(rc PUBSUB CHANNELS | sort)
echo "$CHANNELS" | sed 's/^/  /'
BARE=$(echo "$CHANNELS" | grep -cE '^(task:cancel|settings:changed|model_config:changed|pricing:cache_invalidate|tool:cache:invalidate|mcp:cache:invalidate|memory:invalidated|channel:config:changed|approval:response|ws:deliver:)' || true)
[[ "${BARE:-0}" != "0" ]] && flag "存在 ${BARE} 个未带环境前缀的 LambChat 裸通道（跨环境串台风险）"


# ── 8. PostgreSQL 慢 SQL / 体积（pg_stat_statements）───────────
section "8. PostgreSQL 慢 SQL / 体积"
PG_DSN=$(kubectl -n monitoring get secret monitoring-db-auth -o jsonpath="{.data.POSTGRES_DSN}" | base64 -d)
PGSQL_FILE="$DIR/scripts/pg-patrol.sql"
pg_q() { docker exec -i "$PG_CONTAINER" psql "$PG_DSN" -P pager=off -tA "$@"; }
if [[ -n "$PG_DSN" ]]; then
  docker exec -i "$PG_CONTAINER" psql "$PG_DSN" -P pager=off -f - < "$PGSQL_FILE" 2>/dev/null | sed "s/^/  /"
  PG_SLOW=$(pg_q -c "SELECT count(*) FROM pg_stat_statements WHERE mean_exec_time > 100 AND query NOT LIKE '%pg_stat_%'")
  [[ "${PG_SLOW:-0}" != "0" ]] && flag "PG 存在 ${PG_SLOW} 条平均 >100ms 的语句（详见上表）"
  PG_SEQ1=$(pg_q -c "SELECT coalesce(sum(seq_scan),0) FROM pg_stat_user_tables")
  sleep 20
  PG_SEQ2=$(pg_q -c "SELECT coalesce(sum(seq_scan),0) FROM pg_stat_user_tables")
  PG_SEQD=$((PG_SEQ2 - PG_SEQ1))
  echo "  seq_scan 20s 增量: ${PG_SEQD}"
  [[ "${PG_SEQD:-0}" -gt 100 ]] && flag "PG 顺序扫描 20s 内 +${PG_SEQD}（疑似丢索引/大表扫描）"
else
  flag "monitoring-db-auth 缺 POSTGRES_DSN，PG 巡检跳过"
fi

# ── 9. py-spy 热点（可选）──────────────────────────────────────
if [[ "$WITH_PYSPY" == "1" ]]; then
  section "9. py-spy CPU 热点采样（各 15s@50Hz）"
  for tgt in w0 a; do
    case $tgt in
      w0) PID=$(pgrep -f "src.infra.task.worker_main" | head -1) ;;
      a)  PID=$(ss -tlnp "sport = :8011" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | head -1) ;;
    esac
    [[ -z "${PID:-}" ]] && { echo "  $tgt: 未找到进程，跳过"; continue; }
    echo "  -- $tgt (pid=$PID) 最热栈 Top3:"
    timeout 25 "$BIN" record --format raw --pid "$PID" -d 15 --rate 50 -o /tmp/patrol-$tgt.raw >/dev/null 2>&1
    python3 - /tmp/patrol-$tgt.raw <<'PY'
import sys
from collections import Counter
leafs = Counter()
total = 0
for line in open(sys.argv[1]):
    line = line.rstrip()
    if not line or line.endswith(" 0"): continue
    stack, _, cnt = line.rpartition(" ")
    n = int(cnt); total += n
    leafs[stack.split(";")[-1].strip()] += n
for leaf, n in leafs.most_common(3):
    print(f"     {n/total*100 if total else 0:5.1f}%  {leaf[:80]}")
print(f"     (共 {total} 样本；<5% 即基本空闲)")
PY
    rm -f /tmp/patrol-$tgt.raw
  done
fi

# ── 汇总 ────────────────────────────────────────────────────────
section "汇总"
if [[ ${#ATTENTION[@]} -eq 0 ]]; then
  echo "  ✅ 全部干净（巡检 ${WINDOW_MIN}min 窗口）"
  exit 0
else
  echo "  ⚠️  ${#ATTENTION[@]} 项需关注:"
  printf '     - %s\n' "${ATTENTION[@]}"
  exit 1
fi
