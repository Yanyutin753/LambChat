# LambChat 性能监测栈

零代码侵入的开源性能监测方案（单机 k3s 设计）：不改 LambChat 镜像、不加依赖、
不重启发版，即可看到每个 HTTP 接口的耗时分布、Mongo/Redis 操作延迟、出站上游
延迟，并随时对生产进程采 CPU 火焰图定位热点函数。

```
Prometheus ──采集──▶ Grafana 看板
   ├─ Beyla (eBPF)        LambChat Pod 的 HTTP 路由级 RED + 驱动层 DB 操作 + 出站 HTTP
   ├─ node-exporter       主机 CPU/内存/磁盘
   ├─ mongodb-exporter    MongoDB（含集合级延迟）
   └─ redis-exporter      Redis
py-spy（宿主机按需采样） CPU 火焰图 / 线程栈 dump
```

## 前置条件

- 单机 k3s（或单节点 Kubernetes ≥1.28），内核 ≥4.19 且带 BTF（`/sys/kernel/btf/vmlinux` 存在，Beyla eBPF 需要）
- LambChat 已按 `k8s/lambchat.yaml` 部署（本栈从其 secret 与 Deployment env 自动派生数据库凭据）
- 默认占用本机回环端口：3300(Grafana) / 9090(Prometheus) / 9099(Beyla) / 9100 / 9121 / 9216，全部只绑 127.0.0.1

## 部署

```bash
cd k8s/monitoring
bash scripts/apply.sh
```

脚本会：建 `monitoring` 命名空间 → 派生凭据 secret → 下载社区看板 → 应用全部清单 →
等待就绪。Grafana admin 密码首次自动生成，记在 `k8s/monitoring/.grafana-admin-password`
（已 gitignore，勿提交）。

## 访问 Grafana

```bash
ssh -L 3300:127.0.0.1:3300 <你的服务器>   # SSH 隧道
# 浏览器打开 http://127.0.0.1:3300，用户 admin
```

## 看板

| 看板 | 内容 |
|------|------|
| **LambChat 接口性能 (Beyla eBPF)**（自建） | 路由级 QPS/p95/p99/错误率；Mongo+Redis 按操作名的延迟与 QPS；出站 HTTP 按目标主机延迟（LLM 上游、对象存储等） |
| **LambChat MongoDB**（自建） | 操作速率、平均读/写/命令延迟、连接数、常驻内存、集合级读延迟 Top10、各库数据量 |
| **LambChat PostgreSQL**（自建） | 状态/缓存命中率/库体积/死锁；事务速率；SQL 执行耗时与 IO；**慢 SQL Top10（pg_stat_statements，queryid 维度）**；顺序扫描计数（突增=丢索引嫌疑）；表 live/dead 行数 |
| Node Exporter Full（社区 1860） | 主机全景 |
| Redis Dashboard（社区 11835） | Redis 全景 |

### PostgreSQL 监测前置（一次性）

1. PG 侧启用 pg_stat_statements（需重启 PG）：
   `ALTER SYSTEM SET shared_preload_libraries = 'pg_stat_statements';`
   `ALTER SYSTEM SET track_io_timing = on; ALTER SYSTEM SET pg_stat_statements.track = 'all';`
   重启后在 `lamb-agent` 库 `CREATE EXTENSION pg_stat_statements;`
2. 建只读监测角色（密码会记到部署目录 `.pg-mon-password`，root-only）：
   `CREATE ROLE monitor_exporter LOGIN PASSWORD '...' NOSUPERUSER; GRANT pg_monitor TO monitor_exporter; GRANT CONNECT ON DATABASE "lamb-agent" TO monitor_exporter;`
3. `gen-db-secret.sh` 会把 `POSTGRES_DSN` patch 进 `monitoring-db-auth`（重建 secret 不漂移）；
   `41-postgres-exporter.yaml` 默认关着 `stat_statements`/`long_running_transactions` 两个
   collector——本仓库部署形态已显式开启。

checkpoint 数据治理见 `CHECKPOINT-RETENTION.md`（现状 6.1GB 活 fork 历史；磁盘余量充足，
采用只监控不删策略，TTL 方案待产品确认）。

指标命名注意：Beyla 3.x 用 OTel 语义命名，无 `beyla_` 前缀——
`http_server_request_duration_seconds`（标签 `http_route`）、
`db_client_operation_duration_seconds`（`db_system_name`/`db_operation_name`）、
`http_client_request_duration_seconds`（`server_address`）。

## py-spy CPU 火焰图

```bash
cd k8s/monitoring/scripts
./pyspy.sh record a 60        # 录制 lambchat-a 60s 火焰图 → ../profiles/a-*.svg
./pyspy.sh dump a             # 立即打印所有线程调用栈（查挂起/卡死）
```

首次运行自动下载 py-spy。宿主机直跑（root），不进 Pod、不改生产文件系统，采样
50Hz 开销极低。SVG 浏览器直接打开。

> 多分片部署时目标写 `a` / `b`（按 hostNetwork 端口 8011/8012 反查进程），
> arq worker 副本写 `w0` / `w1`。单副本部署可自行按 `ps` 找 PID 后
> `bin/py-spy record --pid <PID> -d 60`。

## 排查套路

1. 慢接口 → 「LambChat 接口性能」路由 p95 Top10
2. 慢在 DB 还是 CPU → 同看板 DB p95 面板 + Node Exporter CPU
3. 哪个集合慢 → 「LambChat MongoDB」集合读延迟 Top10
4. 哪个函数吃 CPU → `./pyspy.sh record a 60` 看火焰图
5. 请求挂死 → `./pyspy.sh dump a` 看线程栈

## 运维

```bash
bash scripts/apply.sh               # 幂等重装/更新
bash scripts/setup-dashboards.sh    # 只刷新看板（ConfigMap 热加载约 1-2 分钟）
kubectl -n monitoring logs ds/beyla # 组件日志
kubectl -n monitoring top pods      # 资源占用

# 完全卸载
kubectl delete ns monitoring
kubectl delete clusterrole beyla-monitoring clusterrolebinding beyla-monitoring
```

Prometheus 数据保留 15 天（PVC 10Gi，local-path）。整套约 600Mi 内存 / 70m CPU。

## 一键巡检

```bash
cd k8s/monitoring/scripts
./patrol.sh              # 巡检最近 60 分钟，退出码 0=干净 / 1=有需关注项
./patrol.sh 240          # 指定窗口（分钟）
./patrol.sh --pyspy      # 追加 py-spy CPU 热点采样（worker+api 各 15s）
```

覆盖：Mongo 慢查询分类（COLLSCAN 告警）/ 僵尸 trace / 后端 ERROR 分布 /
Redis 慢日志与碎片 / API QPS·p95·5xx / 监控栈自检 / pub-sub 通道隔离 /
**PG 慢 SQL Top8（>20ms，pg_stat_statements）+ 库体积 + 顺序扫描 20s 突变**。
Mongo/Redis 容器名按部署环境用 `MONGO_CONTAINER` / `REDIS_CONTAINER` 覆盖；
PG 容器名用 `PG_CONTAINER` 覆盖（默认 1Panel-postgresql-8Oi4，巡检 SQL 在
`pg-patrol.sql`）。适合接 cron 或外部告警（凭退出码）。

## 坑位备忘

- **hostNetwork 单副本 Deployment 必须 `strategy: Recreate`**：默认 RollingUpdate
  先起新 Pod，新 Pod 因端口被旧 Pod 占用无法调度，旧 Pod 又等新 Pod Ready，死锁。
  清单已全部配置，新增 Deployment 时注意。
- grafana.com 的 mongodb(25800) / beyla(19565) 看板 ID 实际下载到的是无关看板，
  勿引用；Mongo/Beyla 数据由本目录自建看板覆盖。
- 大看板（>256KB）生成 ConfigMap 别走 `kubectl apply`（last-applied 注解超限），
  用 create/replace（setup-dashboards.sh 已处理）。
- py-spy 0.4.x 起无独立 tarball，pyspy.sh 从 release wheel 里解二进制。
- 容器内默认无 CAP_SYS_PTRACE，yama ptrace_scope=1 下 kubectl exec 进容器跑
  py-spy 会拒绝附着——所以 pyspy.sh 在宿主机直跑。
