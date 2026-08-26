# LambChat 分布式部署测试报告

- 日期：2026-08-26
- 测试环境：yang 服务器 `/data/lambchat-test/`（https://test.lambchat.com）
- 镜像：`ghcr.io/yanyutin753/lambchat:main-20260825-171824`（与当日生产一致）
- 结论：**核心分布式能力全部验证通过**；发现 1 个已知限制（运行中任务不跨副本接管）与 2 个环境级注意事项。

## 1. 测试环境拓扑

```
客户端
  └─ openresty (443, TLS) ── 反代 127.0.0.1:8010
       └─ lambchat-test-nginx (轮询负载均衡)
            ├─ lambchat-test-1 (127.0.0.1:8001, 内嵌 arq worker)
            └─ lambchat-test-2 (127.0.0.1:8002, 内嵌 arq worker)

共享状态层（全部独立于生产）：
  ├─ Redis  127.0.0.1:6380（arq 队列 / pubsub / 并发槽 / 调度锁 / SSE Stream）
  ├─ Mongo  127.0.0.1:27018（agent_state_test：会话/配置/审批等 33 集合）
  └─ PG     lamb-agent-test 库（LangGraph checkpoints / store 表结构）
```

多实例协同的关键设计（与 `docs/backend-distributed-performance-audit.md` 一致）：

| 机制 | 实现 | 分布式语义 |
|------|------|-----------|
| 任务执行 | arq 队列（Redis），每副本内嵌 worker | 任意副本提交，任意 worker 竞争消费 |
| SSE 流 | 事件写 Redis Stream，订阅端任意副本读 | 订阅副本 ≠ 执行副本 |
| WebSocket | Redis 路由集合 + `ws:deliver:<instance_id>` 频道 | 连接副本 ≠ 事件产生副本 |
| 配置热更新 | `settings/model_config/channel` 等 pubsub 频道 | 一副本变更，全体失效本地缓存 |
| 会话状态 | LangGraph checkpointer → 共享 PG | 任意副本可恢复任意会话 |
| 调度去重 | `scheduler:task_lock:{task_id}`（SET NX EX 600 + Lua 释放/续期） | 同一任务单实例执行 |

## 2. 测试矩阵与结果

| # | 测试项 | 方法 | 结果 |
|---|--------|------|------|
| T1 | 负载均衡轮询 | 经 nginx 连发 8 请求，按副本日志计数 | ✅ 4:4 均衡 |
| T2 | JWT 跨副本互通 | 8010 登录取 token，分别直打 8001/8002 | ✅ 均 200（同 `JWT_SECRET_KEY`） |
| T3 | 会话跨副本读写 | 8001 创建会话 → 8002 详情/列表 | ✅ 可见可读（Mongo 共享） |
| T4 | arq 跨副本消费 | 多次提交观察认领方 | ✅ 提交/执行副本独立（双向均出现） |
| T5 | SSE 跨副本订阅 | 8001 提交执行，8002 带 run_id 订阅 | ✅ 完整 8 事件（user:message→…→done） |
| T6 | checkpoint 跨副本 | 第 3 轮换副本提交，问上一轮问题 | ✅ 模型准确复述前文；PG checkpoints 30 行 |
| T7 | 配置热更新广播 | 8001 PUT 模型配置 → 观察 8002 日志 | ✅ 收到通知并清 4 条本地 LLM 缓存（自实例正确过滤） |
| T8 | WebSocket 跨实例投递 | 8001 建 ws 连接，8002 进程内 `send_to_user_with_broadcast` | ✅ 8001 连接实时收到消息 |
| T9 | 上传文件跨副本 | 8001 上传 → 8002 读取 | ✅（OSS 共享存储模式，同生产）；本地模式见 §4.3 |
| T10 | 同会话并发提交 | 同 session 同时 2 条消息 | ✅ 双 run 均被认领执行、状态 completed、无重复无丢失 |
| T11 | 故障转移（杀副本） | 执行中 docker stop 副本 2 | ✅ nginx 秒切；停机期间新任务完整执行；副本恢复后轮询回归 2:2 |
| T12 | 定时任务调度锁 | 代码级确认 + Redis 锁 key 设计 | ✅ 机制确认（见 §4.2）；reconcile job 双副本各跑为设计行为（幂等同步） |
| T13 | 生产无回归 | 全程生产 health/容器状态 | ✅ 200 / healthy，未重启 |

## 3. 关键测试详情

### 3.1 arq 跨副本消费（T4）

多次提交后 arq worker 认领分布（日志证据）：

- `run_20260826051727`：8001 提交 → **8002** worker 认领执行
- `run_20260826051946`：8001 提交 → **8001** worker 认领执行
- `run_20260826052155`：8002 提交 → **8001** worker 认领执行
- `run_20260826053704` ×2：并发提交 → 均由 **8002** 认领

两个内嵌 worker 平等竞争同一 Redis 队列，消费分布与提交副本无关，符合分布式队列语义。

### 3.2 SSE 跨副本（T5）

SSE 端点（`GET /api/chat/sessions/{sid}/stream?run_id=...`）从 **Redis Stream** 读取（`dual_writer.read_from_redis`），与执行副本解耦。实测执行在 8001、订阅在 8002，收到完整事件流：

```
event: user:message / thinking×2 / message:chunk×2 / token:usage / metadata / done
```

### 3.3 上下文跨副本延续（T6）

第 1、2 轮在 8001 提交执行，第 3 轮改由 8002 提交（实际被 8001 worker 认领执行）。模型准确回答「你的上一个问题是：‘用一句话回答：天空为什么是蓝色的？’」——会话 checkpoint 经共享 PG 跨副本恢复成功（`checkpoints` 表 30 行写入测试库）。

### 3.4 故障转移（T11）

1. 提交长任务（写诗）→ 8002 认领执行
2. 3 秒后 `docker stop lambchat-test-2`
3. nginx（8010）持续 200（upstream 失败剔除生效）；8001 直接可用
4. **停机期间提交新任务**：完整执行，SSE 收到含模型回复的全部事件
5. `docker start` 恢复 8002 → healthy → 轮询回归 2:2

### 3.5 WebSocket 跨实例投递（T8）

8001 容器内建立 `ws://127.0.0.1:8001/ws?token=...` 连接；8002 容器进程内调用 `send_to_user_with_broadcast(user_id, {...})`。8001 侧连接实时收到：

```
WS_RECEIVED: {"type": "dist-test-broadcast", "from": "replica-2-process", ...}
```

路由链路（Redis `ws:route:{user_id}` 实例注册集合 → `ws:deliver:<instance_id>` 频道定向投递）工作正常。

## 4. 发现的问题与已知限制

### 4.1 【已知限制】执行副本死亡时，运行中任务中断且不自动接管

T11 中被 `docker stop` 的副本上正在执行的任务（`run_20260826053224`）随进程死亡，另一副本**未重新认领**该 arq job，任务中断（无完成/失败事件）。arq worker 的 job 重试未覆盖「执行中进程死亡」场景。

影响：副本崩溃时其上运行中的对话轮需要用户重发。
建议：后续可在 `run_agent_task` 层引入幂等恢复（启动时扫描 running 状态超时 run 重新入队），或配置 arq `retry` + 业务幂等键。**不阻塞多副本部署**（新请求不受影响）。

### 4.2 【机制确认，未端到端实测】定时任务执行锁

`scheduler:task_lock:{task_id}`（`SET NX EX 600`，Lua 原子释放/续期，`runner.py` 注释 "multi-instance dedup"）+ 分布式调度槽设计正确。测试环境无定时任务数据（种子刻意排除 `scheduled_tasks`，防止测试环境双跑生产任务），未观察到真实触发竞争。`Scheduled task reconcile` 内部 job 在两副本各自运行为**设计行为**（幂等地将 Mongo 任务同步到本地 APScheduler）。

### 4.3 【环境注意事项】运行时配置（system_settings）覆盖环境变量

LambChat 启动时从 Mongo `system_settings` 加载运行时配置并**覆盖进程环境变量**（连接串、S3 开关等均在其中）。克隆环境时若不修正，副本会按种子里的生产连接配置运行（本次测试已修正为测试值）。同理：

- 生产 `docker-compose.yml` 中硬编码的 `JWT_SECRET_KEY` / `MCP_ENCRYPTION_SALT` / `HUMAN_APPROVAL_TOOLS` 不会随 `.env` 复制，克隆环境需显式补齐（JWT/SALT 缺失会导致加密数据无法解密、登录态不互通）。
- 上传存储：生产为阿里云 OSS（共享对象存储，天然多副本兼容，已实测跨副本上传/读取）。克隆环境建议关闭 S3 走本地共享卷，或显式指向独立桶。本次实测本地模式未完全生效（`LOCAL_STORAGE_PATH` 默认 `./uploads` 但文件未落共享目录，GET 返回 302），生产不受影响，留待环境侧跟进。
- 分布式校验开关 `LAMBCHAT_REPLICA_COUNT>1` 要求 S3 共享存储（`distributed_validation.py`）；同机多副本共享卷场景未开启该开关，功能不受影响。

### 4.4 【未触发】HITL 审批端到端

配置 `HUMAN_APPROVAL_TOOLS=["bash"]` 后，测试消息中模型未实际调用 bash 工具（直接作答），未产生审批请求。审批数据结构为共享 Mongo `approvals` 集合 + 已验证的 WebSocket 跨实例投递，架构上支持「审批人连接副本 ≠ 任务执行副本」，端到端留待后续补充（需诱导模型真实调用工具）。

## 5. 结论

在 2 副本对称拓扑（内嵌 arq worker）下，LambChat 的多实例协同核心路径——**负载均衡、认证互通、会话/上下文共享、任务队列竞争消费、SSE/WebSocket 跨实例投递、配置缓存失效广播、并发控制、故障转移与自愈**——全部实测通过。状态完全外置于 Redis/Mongo/PG/对象存储，无进程本地状态依赖，**满足水平扩展（对称扩容）部署要求**。

唯一的功能性缺口为 §4.1（执行中任务不跨副本接管），属于故障恢复增强项，不阻塞日常多副本运行。

## 附录：测试环境搭建要点

- 测试环境位于 yang `/data/lambchat-test/`（compose 含 2 副本 + nginx + 独立 Redis + 独立 Mongo），入口 https://test.lambchat.com（openresty + LE 证书，`renew-cert.sh` 自动续期）。
- 数据隔离：Mongo `agent_state_test`（33 个配置集合从生产种子复制，排除 sessions/checkpoints/scheduled_tasks/push_subscriptions 等运行数据）、PG `lamb-agent-test`（仅表结构）、Redis 6380。
- 注意：**Redis PUBLISH/SUBSCRIBE 不按 db 隔离**，多环境必须使用独立 Redis 实例；1Panel openresty 前置 WAF 会拦截未注册域名（需在面板建站或关闭 `unknownWebsite` 规则并重启 openresty）。
